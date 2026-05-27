# BRIDGE_USAGE — how to actually use the bridge

Companion to `BRIDGE_SPEC.md` (the frozen contract). This doc is the
**operator manual**: how to call each adapter from Python and the CLI,
common workflows, and the per-DB gotchas.

The contract: **one Python entry point, one CLI wrapper, every DB
the same shape.**

```python
from lib.bridge_client import bridge_query   # generic
rows = list(bridge_query("interpro", "interpro_entry_by_accession",
                          params={"accession": "IPR011615"}))
```

```bash
python3 -m lib.bridge_client \
  --db interpro --endpoint interpro_entry_by_accession \
  --params accession=IPR011615 \
  --output ipr.jsonl
```

No SKILL.md, no LLM, no per-DB client to learn. The CLI lists what's
available — `--list-dbs` shows every registered DB, `--list-endpoints
--db <id>` shows that DB's endpoint catalogue.

---

## Quick reference — every DB

### `--list-dbs`

```
interpro       experimental   InterPro
uniprot        experimental   UniProt
ncbi           experimental   NCBI E-utils (Entrez)
pdb            experimental   PDB / RCSB
ucsc           planned        UCSC Genome Browser
unibind        planned        UniBind
string         planned        STRING-DB
reactome       experimental   Reactome
quickgo        experimental   QuickGO
pubmed         experimental   PubMed (NCBI E-utils)
```

7 experimental (adapters shipped) + 3 planned (registry only).

---

## Per-DB cookbook

### InterPro — protein domains, families, sites

> What does protein P04637 look like through InterPro's lens?

```bash
python3 -m lib.bridge_client --db interpro \
  --endpoint interpro_entries_by_protein \
  --params accession=P04637 --output p04637_domains.jsonl
```

> What is IPR011615?

```bash
python3 -m lib.bridge_client --db interpro \
  --endpoint interpro_entry_by_accession \
  --params accession=IPR011615
```

> All known PDB structures for the IPR011615 domain:

```bash
python3 -m lib.bridge_client --db interpro \
  --endpoint interpro_structures_by_entry \
  --params accession=IPR011615 --output ipr_structures.jsonl
```

**Gotchas:**
- Always use **UniProt accessions** (P04637), never gene names. Resolve via UniProt search first.
- 16 source DBs (Pfam, CATH-Gene3D, SMART, CDD, …) feed InterPro — pick the right `entry` source if you need a specific signature.

---

### UniProt — sequences, gene-name resolution, cross-refs

> Resolve a gene name to an accession (catfish):

```bash
python3 -m lib.bridge_client --db uniprot \
  --endpoint uniprot_search \
  --params "query=gene:foxp2 AND organism_id:7955,size=5,fields=accession,id,gene_names" \
  --output foxp2_zebrafish.jsonl
```

> Full record for an accession:

```bash
python3 -m lib.bridge_client --db uniprot \
  --endpoint uniprot_entry --params accession=P04637 --output p04637.jsonl
```

> Reference proteome for a species:

```bash
python3 -m lib.bridge_client --db uniprot \
  --endpoint uniprot_proteome --params accession=UP000437414 \
  --output cgariepinus_proteome.jsonl
```

**Gotchas:**
- `query=` uses the UniProt query language: `gene:`, `organism_id:`, `keyword:`, `xref:`, etc. Quote the whole `--params` string.
- For catfish: there's no Clarias gariepinus reference proteome yet — use the Cgar UniProt sub-proteomes that exist, or fall back to ortholog walks via zebrafish (`organism_id:7955`).

---

### NCBI E-utils — gene / taxonomy / nucleotide

The Swiss-army knife. Three steps cover most needs: **esearch** → **esummary** → **efetch**.

> Find Clarias gariepinus's taxonomy id:

```bash
python3 -m lib.bridge_client --db ncbi --endpoint ncbi_esearch \
  --params "db=taxonomy,term=Clarias gariepinus"
# → idlist: ["2724128"]
```

> Pull all genes on Clarias gariepinus chromosome:

```bash
python3 -m lib.bridge_client --db ncbi --endpoint ncbi_esearch \
  --params "db=gene,term=txid2724128[ORGN],retmax=200" \
  --output cgar_genes_ids.jsonl

python3 -m lib.bridge_client --db ncbi --endpoint ncbi_esummary \
  --params "db=gene,id=<comma-separated ids from previous>" \
  --output cgar_genes_summary.jsonl
```

> Walk gene → assembly via elink:

```bash
python3 -m lib.bridge_client --db ncbi --endpoint ncbi_elink \
  --params "dbfrom=gene,db=assembly,id=12345"
```

**Gotchas:**
- 3 req/sec ceiling without an API key. Set `api_key=…` query param on every call for 10/sec.
- E-utils `id` accepts comma-separated lists — batch up to 200 ids per call to stay under rate limits.

---

### PDB / RCSB — protein structures

> All PDB structures linked to a UniProt accession:

```bash
python3 -m lib.bridge_client --db pdb --endpoint pdb_uniprot_xref \
  --params accession=P04637 --output p04637_pdb.jsonl
```

> Full entry record for 1ATP:

```bash
python3 -m lib.bridge_client --db pdb --endpoint pdb_entry \
  --params entry_id=1ATP --output 1ATP.jsonl
```

> Per-chain details:

```bash
python3 -m lib.bridge_client --db pdb --endpoint pdb_polymer_entity \
  --params "entry_id=1ATP,entity_id=1"
```

**Gotchas:**
- entry_id must be uppercase (RCSB's API is case-sensitive on path segments).
- `polymer_entity` IDs are per-entry integers (1, 2, …) — get them from `pdb_entry`'s `rcsb_entry_container_identifiers.polymer_entity_ids`.

---

### Reactome — curated pathways

> Top-level pathways for a species:

```bash
python3 -m lib.bridge_client --db reactome \
  --endpoint reactome_top_pathways_by_species \
  --params "species=Danio rerio" --output zfish_top_pathways.jsonl
```

> Walk a pathway's child events:

```bash
python3 -m lib.bridge_client --db reactome \
  --endpoint reactome_pathway --params stable_id=R-HSA-1640170
```

> Resolve any Reactome identifier (event, entity, protein):

```bash
python3 -m lib.bridge_client --db reactome \
  --endpoint reactome_query --params stable_id=R-HSA-1640170
```

> Static interactors for a UniProt accession:

```bash
python3 -m lib.bridge_client --db reactome \
  --endpoint reactome_interactors_for_uniprot \
  --params accession=P04637 --output p04637_interactors.jsonl
```

**Catfish caveat:** Reactome doesn't directly annotate Clarias. Walk via zebrafish (`Danio rerio`) ortholog UniProt accessions; acknowledge the by-orthology inference in the methods chunk.

---

### PubMed — literature lookup for citations

> Find papers on catfish chromosomal inversions:

```bash
python3 -m lib.bridge_client --db pubmed --endpoint pubmed_search \
  --params "term=Clarias gariepinus[ORGN] AND inversion,retmax=20" \
  --output cgar_inversion_hits.jsonl
```

> Get citations for a list of PMIDs (populate references.jsonl):

```bash
python3 -m lib.bridge_client --db pubmed --endpoint pubmed_summary \
  --params "id=33237286,30357406,28729018" --output citations.jsonl
```

> Pull abstracts:

```bash
python3 -m lib.bridge_client --db pubmed --endpoint pubmed_abstract \
  --params "id=33237286" --output pmid33237286.txt
```

**Gotchas:**
- Same rate limit as the `ncbi` adapter (they share `eutils.ncbi.nlm.nih.gov`). Calls are counted globally per IP.
- `db` param defaults to `pubmed` — you can omit it on every endpoint call.

---

### QuickGO — Gene Ontology terms + annotations

> Look up GO terms:

```bash
python3 -m lib.bridge_client --db quickgo --endpoint quickgo_term \
  --params "ids=GO:0008150,GO:0003674,GO:0005575"
# (BP, MF, CC roots)
```

> Walk a term's ancestors (collapse a fine-grained term to a category):

```bash
python3 -m lib.bridge_client --db quickgo \
  --endpoint quickgo_term_ancestors --params ids=GO:0006281
# (DNA repair → top of the BP hierarchy)
```

> Per-gene GO annotations (catfish):

```bash
python3 -m lib.bridge_client --db quickgo \
  --endpoint quickgo_annotation_search \
  --params "taxonId=7955,goId=GO:0006281,limit=100" \
  --output zfish_dna_repair_gp.jsonl
```

> Per-protein GO annotations:

```bash
python3 -m lib.bridge_client --db quickgo \
  --endpoint quickgo_annotation_search \
  --params "geneProductId=Q5VWG2,limit=50"
```

**Gotchas:**
- `annotation_search` requires at least one of `geneProductId`, `goId`, or `taxonId` — empty query returns 400.
- GO term IDs include the prefix: `GO:0008150` not `0008150`.

---

### UCSC Genome Browser — assemblies, tracks, conservation

> What assemblies does UCSC host?

```bash
python3 -m lib.bridge_client --db ucsc --endpoint ucsc_list_genomes
```

> Tracks on zebrafish:

```bash
python3 -m lib.bridge_client --db ucsc --endpoint ucsc_list_tracks \
  --params genome=danRer11 --output zfish_tracks.jsonl
```

> Conservation scores (phastCons) at a coordinate window:

```bash
python3 -m lib.bridge_client --db ucsc --endpoint ucsc_track_data \
  --params "genome=danRer11,track=phastCons100way,chrom=chr1,start=1000000,end=1010000" \
  --output zfish_chr1_phastcons.jsonl
```

> Reference sequence flanks for a breakpoint:

```bash
python3 -m lib.bridge_client --db ucsc --endpoint ucsc_sequence \
  --params "genome=danRer11,chrom=chr27,start=12420000,end=12440000"
```

**Gotchas:**
- Cap windows to **≤ 1 Mb per call**. UCSC throttles silently above that.
- Track names are case-sensitive. Use `ucsc_list_tracks` first to confirm.
- For Clarias gariepinus, walk via zebrafish coordinates (cross_species_atlas synteny block table) — see the catfish caveat in `bridge/ucsc/LICENSE_NOTICE.md`.

---

### UniBind — curated TF binding profiles

> Browse available TFs:

```bash
python3 -m lib.bridge_client --db unibind --endpoint unibind_factors \
  --output tfs.jsonl
```

> Find FoxA1 TFBS datasets in zebrafish:

```bash
python3 -m lib.bridge_client --db unibind --endpoint unibind_datasets \
  --params "species=Danio rerio,tf_name=FOXA1" \
  --output zfish_foxa1_datasets.jsonl
```

> Single dataset detail (with BED URL):

```bash
python3 -m lib.bridge_client --db unibind --endpoint unibind_dataset_detail \
  --params dataset_id=EXP054321
```

**Gotchas:**
- UniBind covers 9 species; Clarias gariepinus isn't one. Walk via zebrafish — see the caveat in `bridge/unibind/LICENSE_NOTICE.md`.
- Each dataset record carries a BED URL for the binding sites — download separately (the API returns metadata only).

---

### STRING-DB — PPI networks + functional enrichment

> Resolve gene names → STRING IDs (catfish, taxonId 2724128):

```bash
python3 -m lib.bridge_client --db string --endpoint string_resolve_ids \
  --params "identifiers=tp53%0dhba1%0dmdm2,species=2724128"
```

> PPI network for a protein set:

```bash
python3 -m lib.bridge_client --db string --endpoint string_network \
  --params "identifiers=9606.ENSP00000269305,species=9606,required_score=700" \
  --output tp53_network.jsonl
```

> Direct interaction partners (limit per query protein):

```bash
python3 -m lib.bridge_client --db string --endpoint string_interaction_partners \
  --params "identifiers=9606.ENSP00000269305,species=9606,limit=20"
```

> Functional enrichment over a gene list:

```bash
python3 -m lib.bridge_client --db string --endpoint string_enrichment \
  --params "identifiers=ENSDARG00000067846%0dENSDARG00000037780,species=7955" \
  --output zfish_enrich.jsonl
```

**Gotchas:**
- `identifiers` is `%0d`-separated (URL-encoded newline). Most CLI shells require quoting the whole `--params` value.
- `species` is the **NCBI taxonId** (integer). For Clarias gariepinus: `2724128`.
- `required_score` is on the 0–1000 scale (400=medium, 700=high, 900=highest).
- For large lists (>500 ids), batch in chunks of 100 — STRING's response time grows non-linearly above ~500.

---

## Common cross-DB workflows

### A. Gene name → InterPro domain catalogue

```bash
# 1. resolve gene → UniProt
python3 -m lib.bridge_client --db uniprot \
  --endpoint uniprot_search \
  --params "query=gene:tp53 AND organism_id:9606,size=1,fields=accession"
# → P04637

# 2. domains for that accession
python3 -m lib.bridge_client --db interpro \
  --endpoint interpro_entries_by_protein --params accession=P04637 \
  --output tp53_domains.jsonl
```

### B. InterPro domain → 3D structures for the domain

```bash
python3 -m lib.bridge_client --db interpro \
  --endpoint interpro_structures_by_entry \
  --params accession=IPR011615 --output ipr_structs.jsonl
# Then for each row, look up the PDB:
python3 -m lib.bridge_client --db pdb \
  --endpoint pdb_entry --params entry_id=1ATP
```

### C. Catfish gene → ortholog-based pathway enrichment

```bash
# 1. NCBI taxonomy id for Clarias gariepinus
python3 -m lib.bridge_client --db ncbi --endpoint ncbi_esearch \
  --params "db=taxonomy,term=Clarias gariepinus"
# → 2724128

# 2. Resolve catfish gene → UniProt
python3 -m lib.bridge_client --db uniprot \
  --endpoint uniprot_search \
  --params "query=gene:hba1 AND organism_id:2724128,size=1,fields=accession,xref_zfin"
# → catfish accession + zebrafish ortholog xref

# 3. Reactome pathway from zebrafish ortholog
python3 -m lib.bridge_client --db reactome \
  --endpoint reactome_interactors_for_uniprot \
  --params accession=<zebrafish_accession>
```

### D. Catfish breakpoint → conservation + TFBS + interactors (full stack)

The cross_species_atlas's headline workflow: a candidate breakpoint
in Cgar coordinates, looked up across 5 bridge DBs in one chain.

```bash
# 1. Cgar taxonomy id (used everywhere downstream)
python3 -m lib.bridge_client --db ncbi --endpoint ncbi_esearch \
  --params "db=taxonomy,term=Clarias gariepinus"
# → 2724128

# 2. Map breakpoint coords → zebrafish ortholog via the cross_species
#    synteny block table (atlas-side; not a bridge call) → danRer11 chr27:12.43Mb

# 3. UCSC conservation flank for the orthologous coordinate
python3 -m lib.bridge_client --db ucsc --endpoint ucsc_track_data \
  --params "genome=danRer11,track=phastCons100way,chrom=chr27,start=12420000,end=12440000" \
  --output flank_phastcons.jsonl

# 4. UniBind TFBS in the same flank (zebrafish)
python3 -m lib.bridge_client --db unibind --endpoint unibind_datasets \
  --params "species=Danio rerio" \
  --output zfish_tfbs.jsonl   # then filter the BED by flank coords client-side

# 5. STRING PPI network for the genes nearest the breakpoint
python3 -m lib.bridge_client --db string --endpoint string_network \
  --params "identifiers=ENSDARG00000067846%0dENSDARG00000037780,species=7955,required_score=700"

# 6. QuickGO annotations for those same genes (catfish if available, else zebrafish)
python3 -m lib.bridge_client --db quickgo --endpoint quickgo_annotation_search \
  --params "geneProductId=Q5VWG2,limit=50"
```

Cohort discipline: every call is by-orthology against zebrafish (UCSC,
UniBind, STRING, QuickGO species filters all target Danio rerio).
The methods chunk in the manuscript explicitly records this — no
direct Clarias claims inherit from these calls.

### E. Refresh existing references.jsonl from PubMed

For every row in `references.jsonl` that carries a `pmid` or `doi`, fetch the canonical citation from PubMed:

```bash
# Dry-run (default — shows the diff per row, writes nothing)
python3 -m toolkit_registries.relatedness.lib.refresh_references

# One specific row
python3 -m toolkit_registries.relatedness.lib.refresh_references --ref-id Manichaikul2010

# Commit (writes references.jsonl in place; backup at references.jsonl.bak)
python3 -m toolkit_registries.relatedness.lib.refresh_references --commit
```

Per row:
1. Resolve to a PMID — from the row's `pmid` field, or via `pubmed_search` `term=<doi>[doi]` if only a DOI is present.
2. Fetch DocSum via `pubmed_summary`.
3. Build canonical citation from authors + pubdate + title + source + volume + issue + pages.
4. Print diff against existing citation. With `--commit`, write back + record the resolved `pmid` field on the row.

§refusals:
- No writes without `--commit`.
- Skips rows where the DOI lookup is ambiguous (>1 PMID match) — manual disambiguation only.
- Network failures degrade gracefully (printed as warning, row left untouched, exit OK).

### F. Populate references.jsonl from a manuscript draft

```bash
# 1. Find papers
python3 -m lib.bridge_client --db pubmed --endpoint pubmed_search \
  --params "term=Clarias inversion karyotype,retmax=50" --output hits.jsonl

# 2. Get DOI + canonical citation for each PMID
python3 -m lib.bridge_client --db pubmed --endpoint pubmed_summary \
  --params "id=<comma-separated PMIDs>" --output cites.jsonl

# 3. Convert each row into a references.jsonl entry (manual or scripted)
#    {ref_id, citation, doi, url, tags}
```

---

## From Python (when scripting pipelines)

```python
from lib.bridge_client import bridge_query, bridge_count

# Lazy iteration — paginates upstream
for row in bridge_query("interpro", "interpro_proteins_by_entry",
                         params={"accession": "IPR011615", "tax_id": 7955}):
    print(row["metadata"]["accession"])

# Upstream count — NEVER iterate to count
n = bridge_count("interpro", "interpro_entries",
                  params={"type": "domain"})
print(f"InterPro has {n} domain entries")
```

`bridge_query()` yields dicts one at a time and handles pagination,
rate limiting, retries, and caching transparently. `bridge_count()`
reads the `count` / `total` / `n_total` field from a single upstream
response — never iterates.

---

## Caching, audit, and refresh

- Per-endpoint cache TTL is declared in `bridge/<db>/endpoints.json`
  via `cache_seconds`. Hits land in
  `02_queue/bridge_cache/<db>/<endpoint>/<params-hash>.jsonl`.
- Every call (cached or not) appends a line to
  `02_queue/bridge_log.jsonl` with `{ts, db_id, endpoint_id, url,
  ok, elapsed_ms}`.
- Force a fresh fetch with `--no-cache` (CLI) or `use_cache=False`
  (Python).
- Cache files are gitignored (`02_queue/` is runtime state).

## §refusals (carried from BRIDGE_SPEC §6)

1. No re-hosting — cache TTL only.
2. No bypass of upstream ToS — every adapter ships a `LICENSE_NOTICE.md`.
3. No cohort claims — upstream lookups never inherit the 226-cohort `sample_set`.
4. No silent failures — every non-2xx logged + re-raised.
5. No invented endpoints — unknown `endpoint_id` is a hard refusal.
6. No PII / human-subject data.
7. No agentic indirection — direct HTTP, no LLM in the call path.

---

## What's deferred

All 10 v0 bridge adapters now ship working endpoints + LICENSE_NOTICE.md + a cookbook section. Remaining wishlist:

- A conductor `bridge_summary_card` panel showing per-DB call counts + last status, read from `02_queue/bridge_log.jsonl`.
- A per-call provenance handoff to the librarian (`source_kind: bridge` rows in `analysis_results.jsonl`).
- Batched id-list helpers for adapters that need pagination workarounds (STRING above ~500 ids, NCBI EFetch above ~200 ids).

---

_End of BRIDGE_USAGE.md (v0)._
