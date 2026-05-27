#!/usr/bin/env python3
"""
refresh_references.py — refresh references.jsonl citation strings from PubMed.

Closes the loop set up by the pubmed bridge (PR #49). For each row in
references.jsonl that carries either a `pmid` or a `doi`, this script:

  1. resolves the row to a PMID (via the pmid field, or via
     bridge_query('pubmed', 'pubmed_search', term='<doi>[doi]'))
  2. fetches the DocSum (bridge_query('pubmed', 'pubmed_summary',
     id='<pmid>'))
  3. builds a canonical citation string from DocSum fields
  4. compares to the existing citation; prints a diff (dry-run) or
     writes the new citation back (--commit)

Default mode is dry-run. --commit overwrites references.jsonl in place
after backing up to references.jsonl.bak.

§refusals:
  - No writes without --commit.
  - Skips rows where the DOI/PMID lookup is ambiguous (>1 PMID matches)
    — the user must disambiguate manually.
  - Preserves all other fields (tags, url) untouched; only `citation`
    changes, and `pmid` is added when resolved.

Per BRIDGE_USAGE §E.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict

REPO = pathlib.Path(__file__).resolve().parents[3]
REG  = REPO / "toolkit_registries" / "relatedness" / "01_registry"
sys.path.insert(0, str(REPO / "toolkit_registries" / "relatedness" / "lib"))


def load_jsonl(p: pathlib.Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def write_jsonl(p: pathlib.Path, rows: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")


# Optional offline cassette: dict[pmid] -> docsum + dict[doi] -> pmid.
# Set by main() when --fixture is passed; replaces bridge calls so the
# script can run inside smoke without network access.
FIXTURE: dict | None = None


def resolve_doi_to_pmid(doi: str) -> str | None:
    if FIXTURE is not None:
        return FIXTURE.get("doi_to_pmid", {}).get(doi)
    from bridge_client import bridge_query
    try:
        hits = list(bridge_query("pubmed", "pubmed_search",
                                  {"term": f"{doi}[doi]", "retmax": 2}, use_cache=True))
    except Exception as e:
        print(f"     ! pubmed_search failed for doi={doi}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    # esearch returns a single doc with esearchresult.idlist[]
    for h in hits:
        if "esearchresult" in h:
            ids = h["esearchresult"].get("idlist", [])
            return ids[0] if len(ids) == 1 else None
        elif isinstance(h, dict) and "uids" in h:
            ids = h.get("uids", [])
            return ids[0] if len(ids) == 1 else None
    return None


def fetch_docsum(pmid: str) -> dict | None:
    if FIXTURE is not None:
        return FIXTURE.get("docsums", {}).get(pmid)
    from bridge_client import bridge_query
    try:
        hits = list(bridge_query("pubmed", "pubmed_summary",
                                  {"id": pmid}, use_cache=True))
    except Exception as e:
        print(f"     ! pubmed_summary failed for pmid={pmid}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    for h in hits:
        # esummary returns {result: {uids:[...], <pmid>: {...}}}
        if "result" in h and pmid in h["result"]:
            return h["result"][pmid]
        if h.get("uid") == pmid:
            return h
    return None


def build_citation(docsum: dict) -> str:
    authors = docsum.get("authors") or []
    author_list = [a.get("name", "") for a in authors if a.get("authtype") == "Author"]
    if not author_list:
        author_list = [a.get("name", "") for a in authors]
    n = len(author_list)
    if n == 0:    author_block = "[no authors listed]"
    elif n <= 6:  author_block = ", ".join(author_list)
    else:         author_block = ", ".join(author_list[:3]) + ", et al."

    pubdate = (docsum.get("pubdate") or "").split(" ")[0]   # "2010" from "2010 Nov 15"
    title   = (docsum.get("title") or "").rstrip(".")
    source  = docsum.get("source") or ""
    volume  = docsum.get("volume") or ""
    issue   = docsum.get("issue") or ""
    pages   = docsum.get("pages") or ""

    cite = f"{author_block} ({pubdate}) {title}. {source}"
    if volume:
        cite += f" {volume}"
        if issue: cite += f"({issue})"
    if pages: cite += f":{pages}"
    cite += "."
    return cite


def diff(old: str, new: str) -> str:
    if old == new:
        return "(no change)"
    return f"\n  - {old}\n  + {new}"


def refresh_row(row: dict) -> tuple[dict, str]:
    """Returns (updated_row, status_line)."""
    rid = row.get("ref_id", "?")
    pmid = row.get("pmid")
    if not pmid and row.get("doi"):
        pmid = resolve_doi_to_pmid(row["doi"])
        if not pmid:
            return row, f"  -  {rid:<25} DOI {row['doi']} did not resolve to a unique PMID (skip)"
    if not pmid:
        return row, f"  -  {rid:<25} no pmid + no doi → skip"
    docsum = fetch_docsum(pmid)
    if not docsum:
        return row, f"  -  {rid:<25} PMID {pmid} returned empty DocSum (skip)"
    new_cite = build_citation(docsum)
    old_cite = row.get("citation", "")
    new_row = dict(row)
    new_row["pmid"] = pmid
    new_row["citation"] = new_cite
    if old_cite == new_cite:
        return new_row, f"  =  {rid:<25} PMID {pmid}  (citation unchanged; pmid recorded)"
    return new_row, f"  ✱  {rid:<25} PMID {pmid}{diff(old_cite, new_cite)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-id",  default="", help="Restrict to one ref_id.")
    ap.add_argument("--commit",  action="store_true",
                    help="Write back to references.jsonl (after creating .bak). Default is dry-run.")
    ap.add_argument("--fixture", default="",
                    help="Path to an offline JSON cassette ({docsums: {pmid: {...}}, "
                         "doi_to_pmid: {doi: pmid}}). When set, bypasses bridge calls — "
                         "used by smoke to exercise the citation-building path without network.")
    args = ap.parse_args(argv)

    if args.fixture:
        global FIXTURE
        FIXTURE = json.loads(pathlib.Path(args.fixture).read_text())

    refs_path = REG / "references.jsonl"
    refs = load_jsonl(refs_path)
    targets = [r for r in refs if not args.ref_id or r.get("ref_id") == args.ref_id]
    if not targets:
        print(f"no rows match --ref-id={args.ref_id!r}")
        return 1

    print(f"refreshing {len(targets)} reference(s) "
          f"({'COMMIT MODE' if args.commit else 'dry-run; use --commit to write'})")
    print()

    out: list[dict] = []
    changed = 0
    for row in refs:
        if args.ref_id and row.get("ref_id") != args.ref_id:
            out.append(row); continue
        new_row, status = refresh_row(row)
        print(status)
        if new_row != row: changed += 1
        out.append(new_row)
    print()
    print(f"  changed: {changed} / scanned: {len(targets)}")

    if args.commit and changed:
        bak = refs_path.with_suffix(".jsonl.bak")
        bak.write_text(refs_path.read_text())
        write_jsonl(refs_path, out)
        print(f"  wrote {refs_path.relative_to(REPO)}  (backup at {bak.name})")
    elif args.commit:
        print("  no changes to commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
