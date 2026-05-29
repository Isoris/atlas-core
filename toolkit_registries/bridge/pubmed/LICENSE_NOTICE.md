# PubMed — attribution

PubMed is operated by the U.S. National Library of Medicine via the
same Entrez Programming Utilities the `bridge/ncbi/` adapter uses;
this slot scopes specifically to `db=pubmed` so callers don't need to
remember the db param.

- Portal: https://pubmed.ncbi.nlm.nih.gov/
- E-utils docs: https://www.ncbi.nlm.nih.gov/books/NBK25497/

PubMed records are public domain.

## Rate limits

Without an NCBI API key: **3 requests per second** ceiling, enforced
globally per IP.  With an API key: **10 requests per second**.

Same key works for ncbi + pubmed adapters since they share the same
infrastructure.

## Use in atlas-core

This adapter is the bridge the manuscript writer (page 12) uses for
**live citation validation**: when a chunk references `[@RefId]`, the
RefId can resolve to a PubMed PMID via `references.jsonl`, and this
adapter fetches the canonical citation string + DOI without manual
copy-paste.

A follow-up CLI (`scripts/refresh_references.py`, deferred) will walk
references.jsonl entries that carry a `pmid` field and refresh their
`citation` text from PubMed esummary.

## Atlas-core compliance

- no re-hosting; cache TTL per endpoint (1 hr search, 30 day summary
  + abstract since PubMed records rarely change after publication)
- 350 ms min interval between calls (3 req/sec ceiling, leaving
  headroom for parallel calls)
- retry on 429/5xx with exp backoff
- call log at 02_queue/bridge_log.jsonl
