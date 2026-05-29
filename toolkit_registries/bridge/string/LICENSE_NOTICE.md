# STRING-DB — attribution

STRING is operated by a consortium led by EMBL, CPR, and SIB.

- Portal: https://string-db.org/
- API docs: https://string-db.org/help/api/
- License: data released under **CC BY 4.0**
- API access policy: https://string-db.org/cgi/access?footer_active_subpage=licensing

The STRING REST API is free for any use. The web service maintainers
ask that callers identify themselves via `caller_identity` on each
call — `bridge/string/endpoints.json` defaults this to `atlas-core`.

## Citation

When publishing work that uses STRING data, cite the most recent
STRING paper:

> Szklarczyk D, Kirsch R, Koutrouli M, et al. (2023). The STRING
> database in 2023: protein–protein association networks and
> functional enrichment analyses for any sequenced genome of
> interest. Nucleic Acids Research 51(D1):D638-D646.

## Catfish coverage

STRING covers **all sequenced genomes** — including Clarias
gariepinus (NCBI taxonId 2724128) — though scores for less-studied
species are predominantly inferred (homology-based + orthology
transfer) rather than experimentally measured. The `species` query
param accepts the NCBI taxonId directly.

## Atlas-core compliance

- no re-hosting; cache TTL per endpoint (1 wk for id resolution,
  1 day for network / enrichment which can shift between releases)
- 500 ms min interval between calls
- `caller_identity=atlas-core` defaulted on every endpoint so STRING
  can attribute traffic
- retry on 429/5xx with exp backoff
- call log at 02_queue/bridge_log.jsonl

The STRING service rate-limits large requests asymmetrically — small
queries (<10 ids) are fast, large queries (>500 ids) can take
seconds. The bridge timeout is 30s; if you hit it, batch the
identifiers in chunks of 100 and merge client-side.
