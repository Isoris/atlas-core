# UCSC Genome Browser — attribution

The UCSC Genome Browser is operated by the Genomics Institute at the
University of California, Santa Cruz.

- Portal: https://genome.ucsc.edu/
- API docs: https://genome.ucsc.edu/goldenPath/help/api.html
- Conditions of use: https://genome.ucsc.edu/conditions.html

UCSC data are free for academic, non-profit, and personal use.
Commercial use requires a UCSC license — review the conditions
carefully if any downstream consumer is commercial.

## Citation

When publishing work that uses UCSC tracks, cite the most recent
UCSC paper:

> Lee CM, Barber GP, Casper J, et al. (2024). UCSC Genome Browser
> enters 25th year. Nucleic Acids Research.

Plus the original paper(s) of any specific track you use (phyloP /
phastCons / multiz / ENCODE — each has its own citation).

## Catfish caveat

UCSC hosts very few teleost genomes directly (zebrafish danRer11 is
the most useful). For Clarias gariepinus tracks, the practical
pattern is:

1. Coordinate-walk Cgar → zebrafish via the cross_species_atlas
   synteny block table
2. Pull UCSC conservation / TFBS at the zebrafish coordinates
3. Hand back to inversion_atlas as a by-orthology annotation —
   never as a per-Cgar-sample claim

This preserves the cohort discipline established in
`CROSS_SPECIES_BREAKPOINTS_WORKFLOW.md` §6.

## Atlas-core compliance

- no re-hosting; cache TTL per endpoint (1 wk for genome / track
  lists, 1 day for actual track data, 30 days for sequence)
- 500 ms min interval between calls
- retry on 429/5xx with exp backoff
- call log at 02_queue/bridge_log.jsonl
- per-call windows capped to ≤ 1 Mb to stay friendly with the UCSC
  servers (no warning if you exceed; the upstream will throttle)
