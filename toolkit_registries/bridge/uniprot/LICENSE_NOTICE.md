# UniProt — attribution

UniProt data is distributed under **Creative Commons Attribution 4.0
International (CC BY 4.0)**:

- License terms: https://www.uniprot.org/help/license
- UniProt portal: https://www.uniprot.org/

## Required attribution

When publishing work that uses UniProt data, cite:

> The UniProt Consortium. (current year). UniProt: the universal
> protein knowledgebase. Nucleic Acids Research.

The most recent canonical citation as of writing is Bateman et al.
2023 (doi:10.1093/nar/gkac1052) — update to the current release's
canonical paper when publishing.

## Atlas-core compliance

atlas-core wraps the public REST API at `rest.uniprot.org`:
- no re-hosting; cache TTL per-endpoint (1 hr for searches, 1 wk for
  fixed-accession entry lookups, 30 days for proteomes)
- 200 ms min interval between calls (50/min ceiling per UniProt's
  fair-use policy)
- full call log at 02_queue/bridge_log.jsonl

CC BY 4.0 permits commercial reuse with attribution; the same applies
to atlas-core's derived layers as long as the upstream citation is
preserved in references.jsonl.
