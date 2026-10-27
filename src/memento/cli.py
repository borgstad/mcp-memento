from __future__ import annotations

from typing import Optional

import typer

from memento import errors, links, runner


app = typer.Typer(
    name="memento",
    help=(
        "UUID-addressed, section-aware CLI for an org-roam knowledge base. "
        "Configure via MEMENTO_ORG_ROAM_DB and/or MEMENTO_ORG_ROAM_DIR environment variables."
    ),
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


@app.command("read", help="Read a node or section.")
def read(
    ref: str = typer.Argument(..., help="A file-UUID (or prefix), optionally :<id_p>."),
    full: bool = typer.Option(False, "--full", help="Return full bodies (no truncation)."),
    whole: bool = typer.Option(
        False,
        "--whole",
        help="If `ref` carries `:<id_p>`, ignore it and read the whole file. Composes with --full.",
    ),
    link_format: links.LinkFormat = typer.Option(
        links.LinkFormat.INLINE,
        "--link-format",
        case_sensitive=False,
        help="How to render `[[id:UUID][Title]]` org links in body text.",
    ),
) -> None:
    try:
        runner.cmd_read(ref, full=full, whole=whole, link_format=link_format)
    except errors.MementoError as exc:
        raise typer.Exit(code=errors.emit(exc.code, exc.message))


@app.command("update", help="Edit a node or section: body (--content), append (--append), or heading title (--title).")
def update(
    ref: str = typer.Argument(..., help="A file-UUID (or prefix), optionally :<id_p>."),
    content: Optional[str] = typer.Option(None, "--content", help="Inline replacement content for the body."),
    content_file: Optional[str] = typer.Option(
        None,
        "--content-file",
        help="Path to a file containing replacement body content. Use '-' for stdin.",
    ),
    append: bool = typer.Option(
        False,
        "--append",
        help="Append --content to the existing body (blank-line separated) instead of replacing.",
    ),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        help="Rename the heading line (section refs only). Stars, TODO keyword, priority, and tags are preserved.",
    ),
) -> None:
    try:
        runner.cmd_update(ref, content=content, content_file=content_file, append=append, title=title)
    except errors.MementoError as exc:
        raise typer.Exit(code=errors.emit(exc.code, exc.message))


@app.command("list", help="List every :memento: file in the knowledge base (ref + title).")
def list_cmd() -> None:
    try:
        runner.cmd_list()
    except errors.MementoError as exc:
        raise typer.Exit(code=errors.emit(exc.code, exc.message))


@app.command("delete", help="Delete a section (heading + subtree) or a whole file.")
def delete_cmd(
    ref: str = typer.Argument(..., help="A section ref `<file-uuid>:<id_p>`, or a bare file UUID (requires --file)."),
    file: bool = typer.Option(
        False,
        "--file",
        help="Required to delete a whole .org file by its file-UUID. Refused without this flag to prevent accidental file destruction.",
    ),
) -> None:
    try:
        runner.cmd_delete(ref, allow_file=file)
    except errors.MementoError as exc:
        raise typer.Exit(code=errors.emit(exc.code, exc.message))


@app.command("usage", help="Show telemetry recorded by the MCP server (calls, chars, words, latency).")
def usage_cmd(
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="ISO date/datetime lower bound (e.g. '2026-05-01' or '2026-05-01T00:00:00+00:00').",
    ),
    tool: Optional[str] = typer.Option(None, "--tool", help="Restrict to one tool name."),
) -> None:
    try:
        runner.cmd_usage(since=since, tool=tool)
    except errors.MementoError as exc:
        raise typer.Exit(code=errors.emit(exc.code, exc.message))


@app.command("search", help="Substring search across titles and bodies of every file in the knowledge base.")
def search_cmd(
    query: str = typer.Argument(..., help="Substring to look for (case-insensitive)."),
    link_format: links.LinkFormat = typer.Option(
        links.LinkFormat.INLINE,
        "--link-format",
        case_sensitive=False,
        help="How to render `[[id:UUID][Title]]` org links in match snippets.",
    ),
) -> None:
    try:
        runner.cmd_search(query, link_format=link_format)
    except errors.MementoError as exc:
        raise typer.Exit(code=errors.emit(exc.code, exc.message))


@app.command("create", help="Create a new :memento: file using the canonical template.")
def create_cmd(
    title: str = typer.Argument(..., help="File title (also drives the slugified filename)."),
    body: Optional[str] = typer.Option(None, "--body", help="Optional initial body for the file-level node."),
) -> None:
    try:
        runner.cmd_create(title, body=body)
    except errors.MementoError as exc:
        raise typer.Exit(code=errors.emit(exc.code, exc.message))


@app.command("insert", help="Insert a new heading into an existing file.")
def insert_cmd(
    file_ref: str = typer.Argument(..., help="File ref (no `:id_p`). Position is chosen by flags."),
    heading: str = typer.Argument(..., help="Heading text (no leading '*' characters)."),
    body: Optional[str] = typer.Option(None, "--body", help="Optional body to write under the new heading."),
    after: Optional[str] = typer.Option(
        None,
        "--after",
        help="Insert as a sibling immediately after this section ref (level matches the target).",
    ),
    parent: Optional[str] = typer.Option(
        None,
        "--parent",
        help="Insert as a child of this section ref (level = target level + 1).",
    ),
    level: Optional[int] = typer.Option(
        None,
        "--level",
        help="Explicit heading level override (rare). Defaults: 1 (no flag) / target level (--after) / target+1 (--parent).",
    ),
) -> None:
    try:
        runner.cmd_insert(
            file_ref,
            heading_text=heading,
            body=body,
            after_ref=after,
            parent_ref=parent,
            level_override=level,
        )
    except errors.MementoError as exc:
        raise typer.Exit(code=errors.emit(exc.code, exc.message))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
