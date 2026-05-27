# BRIDGE_SPEC — wrapping external biological databases

Status: **v0 (frozen contracts).**
Schema versions: `external_db_v1`, `bridge_endpoint_v1`.

> librarian → manager → dispatcher → chain audit → conductor → pages
> *(internal tiers; act on atlas-core's own registry)*
>
> **bridge** *(NEW; act on external public databases)*

The bridge is a parallel tier — not a replacement for the others. It
wraps **public biological databases** (InterPro, UniProt, UCSC,
UniBind, STRING, Reactome, QuickGO, PubMed) so any atlas can query
them through a uniform contract without rebuilding each client. Same
pattern atlas-core already uses for `popstats_server`: declare the
endpoint, register the adapter, every atlas reads from one place.

**Why "bridge" not "skill":** Google's [science-skills](https://github.com/google-deepmind/science-skills)
ships each DB as a `SKILL.md` + a CLI. The intended loop is *LLM
reads SKILL.md → emits CLI command → subprocess runs → LLM parses output* —
one LLM round-trip per call. The bridge tier skips that layer and
hits the underlying REST APIs **directly** from atlas-core code. No
LLM in the loop. No per-call inference cost. The CLI clients in
science-skills are themselves just HTTP wrappers; the bridge reuses
those patterns, drops the agentic frontmatter, and exposes a single
`bridge_query()` function any atlas can import.

**Not in scope:** AlphaGenome (DeepMind's variant-effect predictor)
is intentionally excluded — its training data is human-only and the
public model doesn't generalise to non-human teleosts. Re-evaluate
when a fish-trained variant lands.

---

## §1 Why

Eight atlases, ~95 modules, ~150 layers. None of them currently
queries InterPro, UniProt, or UCSC — yet every manuscript-track
analysis depends on protein-family / gene-track / conservation
context. Google's [science-skills](https://github.com/google-deepmind/science-skills)
repository already ships polished clients for these databases (rate-
limit aware, retry-safe, paginated). Re-implementing them inside
atlas-core would burn months and produce worse code.

The bridge tier captures the principle:

> Don't re-host data. Wrap the public endpoint, cache reasonably,
> hand results back in atlas-core canonical form.

---

## §2 What is in scope

Free-of-charge programmatic endpoints, no human-subject data, no
chemistry-only databases (PubChem etc.). Today's target list:

| DB | endpoint kind | rate-limited? | use |
|---|---|---|---|
| **InterPro**       | REST | yes (HTTP 429 + 408 + 410) | protein domains, families, GO annotations |
| **UniProt**        | REST | yes (50 req/min) | protein sequences, cross-references, isoforms |
| **UCSC**           | REST + DAS | yes | genome conservation tracks, TFBS, chain alignments |
| **UniBind**        | REST | low | curated TF binding profiles |
| **STRING**         | REST | low | protein-protein interaction networks |
| **Reactome**       | REST | low | curated pathway membership |
| **QuickGO**        | REST | yes | Gene Ontology annotations |
| **PubMed (E-utils)**| REST | 3 req/sec | literature lookup for chunk citations |

Out of scope for v0 (skip per cohort discipline):

- **PubChem** — chemistry, not genomics
- **Human-only databases** (GTEx, ENCODE-human-only, OMIM patient data)
- Anything requiring institutional credentials beyond a free account

---

## §3 Architecture (`external_db_v1`)

Each external database gets one row in `01_registry/external_databases.jsonl`:

```jsonc
{
  "db_id":          "interpro",
  "schema_version": "external_db_v1",
  "label":          "InterPro",
  "owner_url":      "https://www.ebi.ac.uk/interpro/",
  "tos_url":        "https://www.ebi.ac.uk/about/terms-of-use/",
  "license":        "EBI terms-of-use (free, attribution required)",
  "base_url":       "https://www.ebi.ac.uk/interpro/api",
  "auth":           "none",
  "rate_limit": {
    "max_concurrent":  5,
    "min_interval_ms": 250,
    "retry_on_status": [408, 429, 500, 502, 503, 504]
  },
  "adapter_dir":    "bridge/interpro",
  "endpoint_count": 6,
  "status":         "experimental",
  "describes":      "Protein families, domains, sites, GO annotations (incl. InterPro-N deep-learning extension)."
}
```

The `adapter_dir` points at a folder under `bridge/<db>/` containing
the client code + endpoint map + license/ToS attribution. See §4.

---

## §4 Adapter folder layout

```
bridge/<db_id>/
├── client.py            small HTTP wrapper: rate-limit + retry + paginate
├── endpoints.json       declarative map of supported endpoints
├── LICENSE_NOTICE.md    attribution snippet (per the database's ToS)
└── README.md            quick reference, examples
```

`endpoints.json` declares each callable in `bridge_endpoint_v1` shape:

```jsonc
{
  "endpoint_id":  "interpro_entries_by_protein",
  "schema_version": "bridge_endpoint_v1",
  "label":        "InterPro entries for a UniProt accession",
  "method":       "GET",
  "path":         "/entry/interpro/protein/uniprot/{accession}",
  "params": {
    "accession":  {"required": true,  "kind": "path"},
    "page_size":  {"required": false, "kind": "query", "default": 20}
  },
  "returns_layer": "interpro_entries",
  "cache_seconds": 86400,
  "describes":    "Domains, families, sites for a given UniProt protein."
}
```

`returns_layer` is the canonical `layer_id` the bridge maps the
response into. The atlas reads `interpro_entries`; doesn't care that
under the hood the bridge called InterPro.

---

## §5 The unified client (`lib/bridge_client.py`)

Single Python entry point any atlas can import:

```python
from lib.bridge_client import bridge_query

rows = bridge_query(
    db_id="interpro",
    endpoint_id="interpro_entries_by_protein",
    params={"accession": "P04637"},
)
```

`bridge_client` is responsible for:

1. Reading `external_databases.jsonl` + the DB's `endpoints.json`.
2. Validating `params` against the endpoint's declaration.
3. Walking the rate_limit policy (concurrent count + min_interval +
   retry-on-status).
4. Paginating lazily (yields rows one page at a time).
5. Optionally caching to `02_queue/bridge_cache/<db_id>/<endpoint>/<hash>.jsonl`
   for `cache_seconds`.
6. Mapping the response into the `returns_layer` shape (the bridge
   adapter's `to_layer(raw)` function).
7. Logging every call to `02_queue/bridge_log.jsonl` for audit.

CLI mirror:

```bash
uv run lib/bridge_client.py
  --db interpro
  --endpoint interpro_entries_by_protein
  --params accession=P04637
  --output entries.jsonl
```

---

## §6 The §refusals

1. **No re-hosting.** The bridge never stores authoritative data; it
   queries upstream and caches with a TTL.
2. **No bypass of upstream ToS.** Each DB's adapter folder ships a
   `LICENSE_NOTICE.md` and (where required) a one-time prompt to the
   user to read the upstream terms.
3. **No cohort claims.** Results from an external DB are coordinate /
   annotation lookups. They never get tagged with the 226-cohort's
   sample_set. The bridge passes through what the upstream gives.
4. **No silent failures.** HTTP 4xx/5xx are logged + surfaced; never
   swallowed. The bridge's `last_status` per call is queryable from
   `bridge_log.jsonl`.
5. **No invented endpoints.** Every callable is declared in the DB's
   `endpoints.json`. Unknown `endpoint_id` is a hard refusal.
6. **No PII / human-subject data.** Adapters that target databases
   containing human patient identifiers are out of scope until a
   separate compliance review.

---

## §7 Relationship to the existing tiers

| tier | acts on | reads from | writes to |
|---|---|---|---|
| librarian | local layers | filesystem + analysis_results | analysis_results.jsonl |
| manager | local readiness | products + questions | (none; computed live) |
| dispatcher | local actions | analysis_registry | 02_queue/<act>.json |
| chain audit | local chains | analysis_registry + modes | (none; computed live) |
| conductor | local panels | panels.jsonl + spawn_rules | (DOM only) |
| **bridge** | **external DBs** | **external_databases.jsonl + bridge/<db>/endpoints.json** | **02_queue/bridge_cache/ + bridge_log.jsonl** |

The bridge is **read-only** with respect to the local registry. It
**produces** layers (per `returns_layer`) that the librarian can
register as `source_kind: bridge`, just like it registers
`source_kind: file` or `source_kind: analysis_result`.

---

## §8 The bridge → librarian handoff

When a bridge response is mapped into a `returns_layer`, the row that
lands in `analysis_results.jsonl` carries:

```jsonc
{
  "result_id":    "bridge_interpro_P04637_2026-05-27",
  "analysis_type": "bridge:interpro",
  "layer_type":   "interpro_entries",
  "path":         "02_queue/bridge_cache/interpro/interpro_entries_by_protein/P04637.jsonl",
  "status":       "complete",
  "_bridge": {
    "db_id":      "interpro",
    "endpoint_id":"interpro_entries_by_protein",
    "params":     {"accession": "P04637"},
    "fetched_at": "2026-05-27T20:30:00Z",
    "ttl_until":  "2026-05-28T20:30:00Z"
  }
}
```

The librarian sees this as a normal resolved layer; manager / chain
audit / conductor downstream tiers don't know or care it came from a
bridge. Caching policy is per-endpoint via `cache_seconds`.

---

## §9 What ships in v0

- `BRIDGE_SPEC.md`               (this file)
- `01_registry/external_databases.jsonl`  9 rows (8 DBs)
- `bridge/interpro/`             working client + endpoints + license
- `bridge/uniprot/`              working client + endpoints + license
- `bridge/_template/`            skeleton for porting more DBs
- `lib/bridge_client.py`         unified entry point + CLI
- `scripts/check_external_databases.py`  validator (smoke step)

Deferred to follow-up PRs:

- The other 6 DB adapters (UCSC, UniBind, STRING, Reactome, QuickGO,
  PubMed)
- AlphaGenome runtime client (needs the alphagenome Python package +
  optional Google Cloud creds)
- Bridge cache eviction CLI
- `bridge_summary_card` conductor panel (per-DB health + last-call
  status)

---

_End of BRIDGE_SPEC.md (v0)._
