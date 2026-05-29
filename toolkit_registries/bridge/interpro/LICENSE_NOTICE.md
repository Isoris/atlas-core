# InterPro — attribution

The InterPro database is operated by EMBL-EBI. Use of the API is
governed by:

- InterPro front page: https://www.ebi.ac.uk/interpro/
- EMBL-EBI terms of use: https://www.ebi.ac.uk/about/terms-of-use/

InterPro combines signatures from multiple member databases (Pfam,
CATH-Gene3D, SUPERFAMILY, PANTHER, CDD, PROSITE Profiles, SMART,
NCBIFam, PROSITE Patterns, PRINTS, HAMAP, PIRSF, SFLD, AntiFam). All
member databases retain their own licensing terms; consult each one
when reusing signatures downstream.

## Citation

When publishing work that uses InterPro data, cite the most recent
InterPro paper (currently Blum et al. 2021, Nucleic Acids Research,
doi:10.1093/nar/gkaa977) plus the relevant member database papers
your work depends on.

## Atlas-core compliance

atlas-core wraps the public REST API for queries only:
- no re-hosting of InterPro data
- per-endpoint cache TTL declared in endpoints.json
- rate-limit honoured via lib/bridge_client.py (250 ms min interval,
  retry on 408/429/5xx)
- full call log at 02_queue/bridge_log.jsonl

For commercial use, contact EBI directly. This skill is for research
on the 226-cohort Clarias gariepinus manuscript + the comparative
18-species cohort; no other use is implied by inclusion in this repo.
