#!/usr/bin/env python3
"""Per-atlas SPECs indexer — called from build/assemble.sh.

For one atlas, copies SPEC markdown files out of the source repo into
$WORKSPACE/atlases/<aid>/specs/{done,todo}/ and writes a
specs_index.json the SPECs page can fetch.

Sources looked at (in order, all optional, all fail-soft):

    <src>/specs_done/*.md     → specs/done/   (status: done)
    <src>/specs_todo/*.md     → specs/todo/   (status: todo)
    <src>/SPECS.md            → specs/SPECS.md (aggregate)
    <src>/docs/SPEC_*.md      → specs/done/   (status: done) — for atlas-core,
                                which keeps SPECs flat under docs/, not in
                                specs_done/. Skipped if the docs/ file would
                                collide with a specs_done/ entry of the same
                                name.

The first `# heading` line is harvested as the row title (falls back to
the file stem).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path


_HEAD = re.compile(r"^#\s+(.+?)\s*$")


def first_heading(md_path: Path) -> str | None:
    try:
        with md_path.open(encoding="utf-8") as fh:
            for line in fh:
                m = _HEAD.match(line)
                if m:
                    return m.group(1).strip()
    except Exception:
        return None
    return None


def index_one_dir(src: Path, dst: Path, ws_prefix: str) -> list[dict]:
    out: list[dict] = []
    if not src.is_dir():
        return out
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".md":
            continue
        shutil.copy2(p, dst / p.name)
        out.append({
            "file": p.name,
            "title": first_heading(p) or p.stem,
            "path": f"{ws_prefix}/{p.name}",
        })
    return out


def index_docs_specs(src_docs: Path, dst: Path, ws_prefix: str,
                     existing_files: set[str]) -> list[dict]:
    """Pick up atlas-core's docs/SPEC_*.md files as done-specs."""
    out: list[dict] = []
    if not src_docs.is_dir():
        return out
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src_docs.glob("SPEC_*.md")):
        if p.name in existing_files:
            continue
        shutil.copy2(p, dst / p.name)
        out.append({
            "file": p.name,
            "title": first_heading(p) or p.stem,
            "path": f"{ws_prefix}/{p.name}",
        })
    return out


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: index_specs.py <atlas_id> <src_repo_root> <out_specs_dir>",
              file=sys.stderr)
        return 2

    atlas_id     = sys.argv[1]
    src_repo     = Path(sys.argv[2])
    out_specs    = Path(sys.argv[3])
    out_specs.mkdir(parents=True, exist_ok=True)

    # workspace-relative URL prefix the browser uses to fetch a copied SPEC.
    # out_specs is .../atlas-workspace/atlases/<aid>/specs; we want the URL
    # path the static-file server serves, which is "atlases/<aid>/specs".
    # Compute from atlas_id rather than trying to derive from path.
    ws_specs_url = f"atlases/{atlas_id}/specs"

    done_entries = index_one_dir(src_repo / "specs_done",
                                 out_specs / "done",
                                 f"{ws_specs_url}/done")
    todo_entries = index_one_dir(src_repo / "specs_todo",
                                 out_specs / "todo",
                                 f"{ws_specs_url}/todo")

    # atlas-core itself keeps SPECs under docs/ (not specs_done/); merge them
    # into the done list. Names that already exist in done/ win.
    existing = {e["file"] for e in done_entries}
    done_entries.extend(index_docs_specs(src_repo / "docs",
                                         out_specs / "done",
                                         f"{ws_specs_url}/done",
                                         existing))

    # SPECS.md aggregate (per-atlas table-of-contents written by hand).
    aggregate_path = None
    src_aggregate = src_repo / "SPECS.md"
    if src_aggregate.is_file():
        shutil.copy2(src_aggregate, out_specs / "SPECS.md")
        aggregate_path = f"{ws_specs_url}/SPECS.md"

    index = {
        "atlas_id":       atlas_id,
        "has_aggregate":  aggregate_path is not None,
        "aggregate_path": aggregate_path,
        "done":           sorted(done_entries, key=lambda r: r["file"]),
        "todo":           sorted(todo_entries, key=lambda r: r["file"]),
    }

    (out_specs / "specs_index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8")

    print(f"    specs_index: {len(index['done'])} done, "
          f"{len(index['todo'])} to-do"
          f"{' (+SPECS.md)' if aggregate_path else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
