# QuickGO — attribution

QuickGO is operated by EMBL-EBI, the same infrastructure as
`bridge/interpro/`.

- Portal: https://www.ebi.ac.uk/QuickGO/
- EMBL-EBI terms of use: https://www.ebi.ac.uk/about/terms-of-use/
- Gene Ontology source: https://geneontology.org/

QuickGO provides a clean REST layer over the canonical Gene Ontology
+ all GO annotation sources.

## Citation

When publishing work that uses GO annotations, cite:

> Binns D, Dimmer E, Huntley R, Barrell D, O'Donovan C, Apweiler R
> (2009). QuickGO: a web-based tool for Gene Ontology searching.
> Bioinformatics 25(22):3045-3046.

Plus the Gene Ontology Consortium reference for the data:

> The Gene Ontology Consortium (2023). The Gene Ontology knowledgebase
> in 2023. Genetics 224(1).

## Catfish caveat

GO annotations for Clarias gariepinus directly are sparse. The
practical pattern for the cross_species_atlas is to query via UniProt
(`geneProductId=Q...`) for the catfish accession; for the inversion
atlas's candidate gene neighborhoods, fall back to a model-fish taxon
(Danio rerio = taxonId=7955) ortholog and acknowledge the by-orthology
inference in the manuscript.

## Atlas-core compliance

- no re-hosting; cache TTL per endpoint (1 day annotation, 1 wk
  ontology terms)
- 300 ms min interval between calls
- retry on 429/5xx with exp backoff
- call log at 02_queue/bridge_log.jsonl
