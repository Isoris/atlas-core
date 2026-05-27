# Reactome — attribution

Reactome is operated by a consortium led by OICR, EMBL-EBI, NYU
Langone, and others.

- Portal: https://reactome.org/
- License: https://reactome.org/license
- Citation policy: https://reactome.org/citation

Reactome data are released under **CC0** (public domain dedication).

## Citation

When publishing work that uses Reactome data, cite the most recent
Reactome paper (Milacic et al., 2024, Nucleic Acids Research) plus
any specific pathway citations the records carry.

## Catfish caveat

Reactome currently covers ~15 model species. Catfish are not directly
annotated. For Clarias gariepinus work, the practical pattern is:

1. Resolve gene → UniProt (catfish accession)
2. Look up the human / zebrafish ortholog
3. Query Reactome with the ortholog's UniProt accession

This delegates pathway annotation to ortholog mapping. Acknowledge
explicitly in the methods that pathway calls are by orthology.

## Atlas-core compliance

- no re-hosting; cache TTL per endpoint (1 day to 1 week)
- 300 ms min interval between calls
- retry on 429/5xx with exp backoff
- call log at 02_queue/bridge_log.jsonl
