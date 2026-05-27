# PDB / RCSB — attribution

The Protein Data Bank is jointly operated by the wwPDB partnership;
the RCSB PDB hosts the public API atlas-core uses.

- Portal: https://www.rcsb.org/
- Data API: https://data.rcsb.org/
- Search API: https://search.rcsb.org/
- License: https://www.rcsb.org/pages/usage-policies

PDB data are in the public domain. Attribution is requested per the
RCSB usage policies.

## Citation

When publishing work that uses PDB data, cite the RCSB / wwPDB papers:

> Berman HM, Westbrook J, Feng Z, Gilliland G, Bhat TN, Weissig H,
> Shindyalov IN, Bourne PE (2000). The Protein Data Bank. Nucleic
> Acids Research, 28:235-242.

Plus the most recent RCSB PDB annual paper for the release year you
cite.

## Atlas-core compliance

- no re-hosting; per-endpoint cache TTL (1 wk for fixed-accession lookups)
- 250 ms min interval between calls
- retry on 429/5xx with exp backoff
- call log at 02_queue/bridge_log.jsonl
