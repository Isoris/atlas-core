# UniBind — attribution

UniBind is operated by the Computational Biology Unit at the
University of Oslo.

- Portal: https://unibind.uio.no/
- About: https://unibind.uio.no/about/
- License: data released under **CC BY 4.0**

## Citation

When publishing work that uses UniBind data, cite the most recent
UniBind paper:

> Puig RR, Boddie P, Khan A, Castro-Mondragon JA, Mathelier A (2021).
> UniBind: maps of high-confidence direct TF-DNA interactions across
> nine species. BMC Genomics 22(1):482.

UniBind cross-references JASPAR profiles — also cite the most recent
JASPAR release when the binding sites you use are JASPAR-derived.

## Catfish caveat

UniBind directly covers Homo sapiens, Mus musculus, Rattus norvegicus,
Drosophila melanogaster, Caenorhabditis elegans, Saccharomyces
cerevisiae, Schizosaccharomyces pombe, Arabidopsis thaliana, and
Danio rerio.

For Clarias gariepinus work, the by-orthology pattern through
zebrafish (`species=Danio rerio`) is the practical path; acknowledge
the inference in the manuscript methods chunk.

## Atlas-core compliance

- no re-hosting; cache TTL per endpoint (1 wk for catalogues, since
  UniBind releases are annual)
- 500 ms min interval between calls
- retry on 429/5xx with exp backoff
- call log at 02_queue/bridge_log.jsonl
