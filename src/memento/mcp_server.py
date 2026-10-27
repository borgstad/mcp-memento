from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from memento import usage


logger = logging.getLogger("memento-mcp")

SERVER_NAME = "memento-mcp"

try:
    SERVER_VERSION = version("mcp-memento")
except PackageNotFoundError:
    SERVER_VERSION = "0.0.0+dev"

server: Server = Server(SERVER_NAME)


class CliError(RuntimeError):
    """Raised when the underlying `memento` CLI exits non-zero or emits non-JSON stdout.

    The string form of the exception is the JSON payload the MCP client should see.
    """


def _run_cli(cmd: str, *args: str) -> dict[str, Any]:
    argv = [sys.executable, "-m", "memento.cli", cmd, *args]
    result = subprocess.run(argv, capture_output=True, text=True, env=os.environ.copy())

    stdout = result.stdout.strip()
    if not stdout:
        raise CliError(
            json.dumps(
                {
                    "error": "io_error",
                    "message": f"memento {cmd} produced no stdout (exit {result.returncode}); stderr: {result.stderr.strip()[:500]}",
                }
            )
        )

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CliError(
            json.dumps(
                {
                    "error": "io_error",
                    "message": f"memento {cmd} stdout was not valid JSON: {exc}",
                    "stdout_snippet": stdout[:500],
                }
            )
        )

    if result.returncode != 0:
        raise CliError(json.dumps(parsed))
    return parsed


def _ok(payload: dict[str, Any]) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False))]


@server.list_tools()  # type: ignore[misc]
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="memento_read",
            description=(
                "Read a node or a single section of the :memento: org-roam knowledge base. "
                "Pass a file ref (`<file-uuid>` or unambiguous prefix) for the whole file, "
                "or `<file-uuid>:<id_p>` for a single section. Use `full=true` for non-truncated "
                "bodies; use `whole=true` to expand a section ref back to its parent file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "File-UUID prefix, optionally `:id_p`. Example: `73f8e2a0:2`.",
                    },
                    "full": {
                        "type": "boolean",
                        "description": "Return full bodies instead of 100-char `short` summaries.",
                        "default": False,
                    },
                    "whole": {
                        "type": "boolean",
                        "description": "If `ref` carries `:id_p`, expand to the whole-file response.",
                        "default": False,
                    },
                    "link_format": {
                        "type": "string",
                        "enum": ["inline", "raw", "title"],
                        "description": "How org `[[id:UUID][Title]]` links render. `inline` (default) = `Title (ref:8charprefix)`; `raw` preserves the org syntax; `title` is lossy.",
                        "default": "inline",
                    },
                },
                "required": ["ref"],
            },
        ),
        types.Tool(
            name="memento_update",
            description=(
                "Replace (or, with `append=true`, extend) the body of a node or section. "
                "Provide either `content` or `content_file`; `content_file=\"-\"` reads stdin "
                "(not useful from MCP). Bytes outside the targeted body are preserved."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "File-UUID prefix, optionally `:id_p`. Example: `73f8e2a0:2`.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Inline replacement content. Preferred from MCP callers.",
                    },
                    "content_file": {
                        "type": "string",
                        "description": "Path to a file containing replacement content.",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Append to existing body (blank-line separated) instead of replacing.",
                        "default": False,
                    },
                    "title": {
                        "type": "string",
                        "description": "Rename the heading line (section refs only). Stars, TODO keyword, priority, and tags are preserved.",
                    },
                },
                "required": ["ref"],
            },
        ),
        types.Tool(
            name="memento_list",
            description="List every file in the knowledge base carrying the `:memento:` filetag.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        types.Tool(
            name="memento_search",
            description=(
                "Case-insensitive substring search over titles and bodies of every "
                ":memento: file. Returns section-level refs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Substring to look for."},
                    "link_format": {
                        "type": "string",
                        "enum": ["inline", "raw", "title"],
                        "description": "How org `[[id:UUID][Title]]` links render in match snippets.",
                        "default": "inline",
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="memento_create",
            description=(
                "Create a new :memento: file using the canonical template. "
                "The filetag `:memento:` is auto-injected. Returns the new file's ref and embeds the full file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "File title."},
                    "body": {
                        "type": "string",
                        "description": "Optional initial body under the file-level node.",
                    },
                },
                "required": ["title"],
            },
        ),
        types.Tool(
            name="memento_insert",
            description=(
                "Insert a new heading into an existing file. Default = append at EOF as `*`. "
                "Use `after` to make a sibling at the target's level; use `parent` to nest one level deeper. "
                "`after` and `parent` are mutually exclusive. Returns the new ref and embeds the full file.\n\n"
                "IMPORTANT: inserting a heading SHIFTS the id_p of every section that comes after the insertion point. "
                "Refs from earlier reads/responses for those later sections are NOW STALE. "
                "Always use refs from THIS response's `file.sections` array for any follow-up call on this file. "
                "Do not reuse refs cached from before this insert."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_ref": {
                        "type": "string",
                        "description": "File ref (no `:id_p`). Position is chosen by `after`/`parent`.",
                    },
                    "heading": {"type": "string", "description": "Heading text (no leading `*` characters)."},
                    "body": {
                        "type": "string",
                        "description": "Optional body to write under the new heading.",
                    },
                    "after": {
                        "type": "string",
                        "description": "Section ref `<file-uuid>:<id_p>`. New heading becomes a sibling at the same level.",
                    },
                    "parent": {
                        "type": "string",
                        "description": "Section ref `<file-uuid>:<id_p>`. New heading nests one level deeper.",
                    },
                    "level": {
                        "type": "integer",
                        "description": "Explicit heading level override (rare).",
                    },
                },
                "required": ["file_ref", "heading"],
            },
        ),
        types.Tool(
            name="memento_delete",
            description=(
                "Delete a section (heading + its subtree) or a whole file. "
                "Section delete: ref is `<file-uuid>:<id_p>`, no flag needed. "
                "Whole-file delete: ref is the bare file UUID and `file=true` is REQUIRED (refused otherwise). "
                "Returns the post-state file for section deletes; just `{ref, deleted}` for file deletes.\n\n"
                "IMPORTANT: deleting a section SHIFTS the id_p of every section that came after it (later sections "
                "all move down by one). Refs from earlier reads/responses for those later sections are NOW STALE. "
                "Always use refs from THIS response's `file.sections` array for any follow-up call on this file. "
                "Do not reuse refs cached from before this delete. Deleting a whole file invalidates every ref into it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "A section ref `<file-uuid>:<id_p>`, or a bare file UUID (then `file` must be true).",
                    },
                    "file": {
                        "type": "boolean",
                        "description": "Must be true to delete a whole .org file. Ignored for section deletes.",
                        "default": False,
                    },
                },
                "required": ["ref"],
            },
        ),
        types.Tool(
            name="memento_version",
            description="Return the version of the `mcp-memento` package this server wraps.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
    ]


def _dispatch_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Pure dispatch — no telemetry. Telemetry is the caller's responsibility."""
    if name == "memento_read":
        args: list[str] = [str(arguments["ref"])]
        if arguments.get("full"):
            args.append("--full")
        if arguments.get("whole"):
            args.append("--whole")
        if (link_format := arguments.get("link_format")) is not None:
            args += ["--link-format", str(link_format)]
        return _ok(_run_cli("read", *args))

    if name == "memento_update":
        args = [str(arguments["ref"])]
        if (content := arguments.get("content")) is not None:
            args += ["--content", str(content)]
        if (content_file := arguments.get("content_file")) is not None:
            args += ["--content-file", str(content_file)]
        if arguments.get("append"):
            args.append("--append")
        if (title := arguments.get("title")) is not None:
            args += ["--title", str(title)]
        return _ok(_run_cli("update", *args))

    if name == "memento_list":
        return _ok(_run_cli("list"))

    if name == "memento_search":
        args = [str(arguments["query"])]
        if (link_format := arguments.get("link_format")) is not None:
            args += ["--link-format", str(link_format)]
        return _ok(_run_cli("search", *args))

    if name == "memento_create":
        args = [str(arguments["title"])]
        if (body := arguments.get("body")) is not None:
            args += ["--body", str(body)]
        return _ok(_run_cli("create", *args))

    if name == "memento_insert":
        args = [str(arguments["file_ref"]), str(arguments["heading"])]
        if (body := arguments.get("body")) is not None:
            args += ["--body", str(body)]
        if (after := arguments.get("after")) is not None:
            args += ["--after", str(after)]
        if (parent := arguments.get("parent")) is not None:
            args += ["--parent", str(parent)]
        if (level := arguments.get("level")) is not None:
            args += ["--level", str(int(level))]
        return _ok(_run_cli("insert", *args))

    if name == "memento_delete":
        args = [str(arguments["ref"])]
        if arguments.get("file"):
            args.append("--file")
        return _ok(_run_cli("delete", *args))

    if name == "memento_version":
        return _ok({"name": SERVER_NAME, "version": SERVER_VERSION})

    raise CliError(json.dumps({"error": "invalid_input", "message": f"unknown tool: {name}"}))


def _input_text(arguments: dict[str, Any]) -> str:
    """All string-valued arguments concatenated, for input size measurement."""
    parts = [str(v) for v in arguments.values() if isinstance(v, str)]
    return "\n".join(parts)


@server.call_tool()  # type: ignore[misc]
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    arguments = arguments or {}
    started = time.perf_counter()
    output_text = ""
    exit_code = 0
    error_code: str | None = None
    try:
        result = _dispatch_call_tool(name, arguments)
        output_text = result[0].text if result else ""
        return result
    except CliError as exc:
        exit_code = 1
        output_text = str(exc)
        try:
            error_code = json.loads(output_text).get("error")
        except json.JSONDecodeError:
            error_code = "io_error"
        raise
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage.record(
            tool=name,
            input_text=_input_text(arguments),
            output_text=output_text,
            latency_ms=latency_ms,
            exit_code=exit_code,
            error=error_code,
        )


async def _serve() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version=SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
