# memento

UUID-addressed, section-aware CLI for an org-roam knowledge base. Primary client is an LLM agent: every call is stateless, JSON-out and aims to be as token-cheap as possible.

## Install

```sh
make install      # uv sync
```

The `memento` entry point is wired in `pyproject.toml`.

## Configure

Configuration is **environment-only**. There are no CLI flags for paths.

| Variable | Purpose | Required |
|---|---|---|
| `MEMENTO_ORG_ROAM_DB` | Path to the org-roam SQLite index. Read-only. | One of these two |
| `MEMENTO_ORG_ROAM_DIR` | Path to the org-roam directory; used as a fallback scanner when the DB is missing or unreadable. | One of these two |

If both are set, the DB is tried first.

```sh
export MEMENTO_ORG_ROAM_DB=~/.emacs.d/org-roam.db
export MEMENTO_ORG_ROAM_DIR=~/syncthing/knowledge-archive/org/roam
```

## Addressing

Every section has a stable **ref** of the form `<file-uuid>:<id_p>` where:

- `<file-uuid>` is the file-level node id (full UUID or any **unambiguous prefix**).
- `<id_p>` is a 1-indexed integer assigned by walking every heading in the file in document order at every depth.

```
* Goals          -> id_p = 1
** Constraints   -> id_p = 2
* Risks          -> id_p = 3
*** Deep         -> id_p = 4
* Next steps     -> id_p = 5
```

The file-level body (the text between the property drawer and the first heading) is addressed by the bare `<file-uuid>` with no `:id_p` suffix.

> **id_p is positional, not stable.** Inserting or removing a heading shifts every subsequent `id_p`. Always read a file immediately before updating one of its sections in the same agent turn; never persist `id_p` across edits.

## Commands

### `memento read <ref> [--full]`

Whole-file read (no `:id_p`), compact form:

```sh
memento read 73f8e2a0
```

```json
{
  "sections": [
    {"ref": "73f8e2a0-...",   "title": "Migration Notes", "short": "We're distilling the large image classifier into a smaller student model. This note tracks the why."},
    {"ref": "73f8e2a0-...:1", "title": "Goals",           "short": "Halve inference latency per image and keep top-1 accuracy within one point."},
    {"ref": "73f8e2a0-...:2", "title": "Constraints",     "short": "Latency budget is 200ms per batch. Must run on the existing GPU queue workers."}
  ]
}
```

The file-level node is the first entry in `sections`; its `ref` is the bare file UUID (no `:id_p`). All other entries are headings in document order.

Whole-file with full bodies:

```sh
memento read 73f8e2a0 --full
```

`short` is replaced with `content` in every entry; bodies are not truncated.

Single section:

```sh
memento read 73f8e2a0:2
```

```json
{"ref": "73f8e2a0-...:2", "title": "Constraints", "content": "Latency budget is 200ms per batch. Must run on the existing GPU queue workers."}
```

`--full` is a no-op on a single-section read.

Search-then-expand flow: after locating an interesting section via `memento search`, you can expand from that ref to the whole containing file:

```sh
memento read 73f8e2a0:2 --whole          # same response as `memento read 73f8e2a0`
memento read 73f8e2a0:2 --whole --full   # whole file, full bodies
```

`--whole` simply ignores the `:<id_p>` portion of the ref and returns the whole-file response. It composes with `--full`. On a bare file-UUID it's a no-op.

### `memento list`

Enumerate every `:memento:`-tagged file as `{ref, title}`.

```sh
memento list
```

```json
{
  "files": [
    {"ref": "73f8e2a0-...", "title": "Migration Notes"},
    {"ref": "aa11bb22-...", "title": "Architecture"}
  ]
}
```

### `memento search <query>`

Case-insensitive substring search across every file's title and every section's body. Returns section-level refs.

```sh
memento search "latency budget"
```

```json
{
  "query": "latency budget",
  "matches": [
    {"ref": "73f8e2a0-...:2", "title": "Constraints", "snippet": "Latency budget is 200ms per batch. Must run on the existing GPU queue workers."}
  ]
}
```

A title match on a file emits the file-level ref (`<uuid>`, no `:id_p`); a body match on a heading emits `<uuid>:<id_p>`. An empty query is an `invalid_input`. No matches returns `matches: []` with exit 0.

### `memento create <title> [--body <text>]`

Write a new memento file using the canonical template (drawer + `#+title:` + `#+filetags: :memento:` + optional body). Filename is slugified from the title; `_<n>` is appended on collision.

```sh
memento create "Migration Notes" --body "We're distilling the image classifier."
```

```json
{
  "ref": "73f8e2a0-...",
  "created": true,
  "file": {"sections": [{"ref": "73f8e2a0-...", "title": "Migration Notes", "short": "We're distilling the image classifier."}]}
}
```

`MEMENTO_ORG_ROAM_DIR` is required for create. The write is race-safe (`O_EXCL`).

### `memento insert <file-ref> <heading> [--body <text>] [--after <ref> | --parent <ref>] [--level N]`

Add a heading to an existing file. Default appends at EOF as `*`. `--after` makes a sibling at the target's level (after its full subtree). `--parent` nests one level deeper. `--level` is an explicit override.

```sh
memento insert 73f8e2a0 "Risks"      --body "concurrent emacs edits"
memento insert 73f8e2a0 "Mitigation" --parent 73f8e2a0:3 --body "use a lockfile"
memento insert 73f8e2a0 "Sibling"    --after  73f8e2a0:2
```

Response carries the new `ref` and the full post-state file (compact form), so the agent doesn't need a follow-up `read`:

```json
{
  "ref": "73f8e2a0-...:4",
  "inserted": true,
  "file": {"sections": [...]}
}
```

### `memento delete <ref> [--file]`

Section delete (heading + subtree) by ref:

```sh
memento delete 73f8e2a0:2     # remove the "Constraints" subtree from migration-notes.org
```

```json
{
  "ref": "73f8e2a0-...:2",
  "title": "Constraints",
  "deleted": true,
  "file": {"sections": [...]}
}
```

Whole-file delete (requires `--file` to prevent accidental destruction):

```sh
memento delete 73f8e2a0           # refused: invalid_input
memento delete 73f8e2a0 --file    # actually unlinks migration-notes.org
```

```json
{"ref": "73f8e2a0-...", "title": "Migration Notes", "deleted": true}
```

### `memento update <ref> --content <body> [--append]`

Replace the body of the targeted node. Content sources, in precedence order:

1. `--content <string>`
2. `--content-file <path>` (use `-` for stdin)

```sh
memento update 73f8e2a0:2 --content "Latency budget is 150ms once the student model ships."
echo "new intro" | memento update 73f8e2a0 --content-file -
```

```json
{"ref": "73f8e2a0-...:2", "updated": true}
```

Bytes outside the targeted body are preserved verbatim, including descendant headings and their bodies. The write is atomic from a concurrent reader's perspective.

`--append` extends the body instead of replacing it (separated by a blank line):

```sh
memento update 73f8e2a0:2 --append --content "Follow-up: confirmed by SRE."
```

## Error contract

Every non-zero exit prints one line of JSON to stdout and exits non-zero:

```json
{"error": "<code>", "message": "<human text>"}
```

| Code | Exit | Cause |
|---|---|---|
| `not_found` | 1 | File-UUID prefix matches nothing; or `id_p` is out of range. |
| `ambiguous_prefix` | 1 | File-UUID prefix matches more than one file. |
| `db_unavailable` | 1 | Neither `MEMENTO_ORG_ROAM_DB` nor `MEMENTO_ORG_ROAM_DIR` is usable. |
| `invalid_input` | 2 | Path-like identifier, non-integer or non-positive `id_p`, missing content on update. |
| `io_error` | 3 | File read/write failed. |

## Scope

Every operation (`read`, `update`, `search`) is restricted to files carrying the `:memento:` filetag. Files without the tag are invisible to the CLI — they will resolve as `not_found` and be skipped by search. This is hard-baked and not configurable in v1, by design (the CLI targets the memento sub-corpus of your knowledge base, the same one the existing org-roam-mcp server uses).

A file is in scope iff its top contains:

```
#+filetags: :memento:
```

(any other tags may follow). Tag matching is case-insensitive on the token, just like org-mode itself.

## File format (for future `create`)

When `memento create` lands, new files will be written in the exact format the existing org-roam-mcp server produces, so re-indexing in emacs is identical:

```
:PROPERTIES:
:ID: <uuid>
:END:

#+title: <title>
#+filetags: :memento:

<body>
```

Property drawer has only `:ID:`/`:END:`; one blank line before `#+title:`; `#+filetags:` always includes `:memento:` (auto-injected); one blank line before the body.

## Caveats

- **Concurrent emacs edits.** If emacs has the file open with unsaved changes, your write may be overwritten when emacs next saves. v1 makes no attempt to coordinate. Either close the buffer or save before invoking `memento update`.
- **Heading `:ID:` is preserved but unused.** If a heading carries its own org-roam `:ID:` property, it stays in the file unchanged. The CLI never accepts or emits heading-level UUIDs.

## Org-roam DB sync

After every write (`create`, `update`, `insert`, `delete`), memento best-effort invokes `emacsclient --eval (org-roam-db-update-file PATH)` (or `(org-roam-db-clear-file PATH)` for file deletes) so the org-roam SQLite index stays current.

Requirements:
- `emacsclient` on `PATH`.
- Emacs running with `(server-start)` (typical in `init.el`).
- org-roam loaded in that emacs session.

If any of those is missing, memento prints a one-line warning to stderr and proceeds — the file change still happens, just the index becomes stale until the user runs `M-x org-roam-db-sync` manually.

Disable the sync entirely with `MEMENTO_NO_SYNC=1` (useful for CI or non-emacs setups).

## Telemetry

The MCP server records every tool call to a local SQLite database (default `~/.local/share/memento/usage.db`, override with `MEMENTO_USAGE_DB`). Each row carries: timestamp, tool name, input chars/words, output chars/words, latency (ms), exit code, and error code (if any). Telemetry writes are best-effort — a failed write logs to stderr but never breaks the user-facing call.

Query the accumulated data via the CLI:

```sh
memento usage                          # totals + per-tool breakdown across all time
memento usage --since 2026-05-01       # only calls since that date
memento usage --tool memento_read      # one tool
```

```json
{
  "since": null,
  "tool": null,
  "totals": {"calls": 142, "input_chars": 8421, "output_chars": 384210, "latency_ms": 5200},
  "by_tool": [
    {"tool": "memento_read", "calls": 96, "input_chars": 3456, "output_chars": 184302, "output_words": 29183, "avg_latency_ms": 38, "errors": 0}
  ]
}
```

## MCP usage

The same package ships an MCP server (`memento-mcp`) that wraps every CLI command as a typed MCP tool.

### Enable for Claude Code

```sh
claude mcp add memento-mcp \
  -s user \
  -e MEMENTO_ORG_ROAM_DB=$HOME/.emacs.d/org-roam.db \
  -e MEMENTO_ORG_ROAM_DIR=$HOME/syncthing/knowledge-archive/org/roam \
  -- uv run --directory /absolute/path/to/mcp-memento memento-mcp
```

- `-s user` registers at the user scope (`~/.claude.json`), so it's available in every Claude Code project. Drop the flag for project-local scope.
- The two `-e` flags pin the knowledge-base paths into the server's environment. Adjust paths to your setup.
- The trailing `-- uv run --directory ... memento-mcp` is the spawn command. The MCP server is a stdio process Claude Code launches on demand.

Verify with:

```sh
claude mcp list | grep memento
# memento-mcp: uv run --directory /.../mcp-memento memento-mcp - ✓ Connected
```

If you previously had `org-roam-memento` registered, retire it now:

```sh
claude mcp remove -s user org-roam-memento
```

### Tool surface

Once registered, the agent sees tools prefixed `mcp__memento-mcp__*`:

| Tool | Wraps |
|---|---|
| `memento_read` | `memento read <ref> [--full] [--whole] [--link-format]` |
| `memento_update` | `memento update <ref> --content [--append]` |
| `memento_list` | `memento list` |
| `memento_search` | `memento search <query> [--link-format]` |
| `memento_create` | `memento create <title> [--body]` |
| `memento_insert` | `memento insert <file_ref> <heading> [--after / --parent / --level]` |
| `memento_delete` | `memento delete <ref> [--file]` |
| `memento_version` | reports the wrapped package version |

The server is a thin shell-out — each tool forks `python -m memento.cli <cmd>`, parses the JSON response, and returns it verbatim. The CLI is the single source of truth for behaviour; the MCP layer does no reshaping, filtering, or augmentation.

### Link rendering

Org `[[id:UUID][Title]]` links are rendered as `Title (ref:8charprefix)` by default. The agent can call `memento_read` with the prefix directly to follow. Override via the `link_format` parameter (`inline` / `raw` / `title`).

## Development

```sh
make test         # full suite (CLI + MCP)
make smoke        # only tests/smoke/
```

Tests live under `tests/` with real fixture `.org` files in `tests/data/roam/`. A session-scoped pytest fixture builds an `org-roam.db` from those files into a tmp path; the SQLite index is never committed.

The capability spec, design, and open-spec change live under `openspec/changes/memento-cli-section-addressable-reads/`.
