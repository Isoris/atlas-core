# LLM_FUNNEL_SPEC — multi-layer controlled vocabulary + staged Q&A resolver

**Status:** v1 design, drafted 2026-05-13. Not implemented; this doc
defines the contract that page 1 (`Conversation`) will satisfy. The
schemas + keyword banks ship alongside this doc so downstream
implementation (any model, any provider) has a stable target.

**Principle:**

> Human words → cleaned request → domain selection → controlled
> vocabulary → registry contracts → action plan.
>
> Each stage has ONE job. The LLM never jumps from vague words straight
> to files. Stage outputs are inspectable, editable, and stable across
> sessions — so any stage can be replayed or tweaked without redoing
> the rest. The contract resolver (stage 5) is **deterministic**; only
> stages 1–3 are LLM calls.

---

## 1. The funnel — five stages, two LLM calls

```
                                       (LLM call #1)
                ┌────────────────────────────────────────────┐
                │                                            │
human request → │   STAGE 1   language cleanup + decomposition │ → decomposition.json
                │                                            │
                └────────────────────────────────────────────┘
                                       │
                ┌──────────────────────▼─────────────────────┐
                │   STAGE 2   domain selection                 │ (deterministic; can be
                │            (from controlled menu)            │  LLM-assisted or rule-based)
                └──────────────────────┬─────────────────────┘
                                       │ → domain_selection.json
                                       │
                                       ▼
                ┌────────────────────────────────────────────┐
                │   STAGE 3   keyword mapping                  │   (LLM call #2;
                │            human terms → controlled vocab    │   loaded ONLY with banks
                │                                              │   for the selected domains)
                └──────────────────────┬─────────────────────┘
                                       │ → keyword_mapping.json
                                       │
                ┌──────────────────────▼─────────────────────┐
                │   STAGE 4   refinement (Q&A)                 │ (deterministic;
                │            ask the user when stage 3 is        only fires if ambiguous /
                │            ambiguous or under-specified        missing required dims)
                └──────────────────────┬─────────────────────┘
                                       │ → refinement_round.json (zero or more)
                                       │
                ┌──────────────────────▼─────────────────────┐
                │   STAGE 5   contract resolution              │ (deterministic;
                │            ↓ against the live registries     │  pure Python; no LLM)
                │   sample_sets / group_sets / interval_sets   │
                │   / site_sets / input_values / analysis_modes│
                │   / module_registry                          │
                └──────────────────────┬─────────────────────┘
                                       │ → contract_resolution.json
                                       │   + an ordered list of action_manifests
                                       ▼
                                action endpoint
                              (POST /api/actions —
                               PR #3 contract)
```

The crucial division:

| Stage | LLM-driven? | Output is shaped by |
|---|---|---|
| 1. Decomposition | yes (call #1) | a single, narrow prompt; output is a strict JSON schema |
| 2. Domain selection | optional LLM; can be rule-based | the controlled `domains.tsv` |
| 3. Keyword mapping | yes (call #2) | ONLY the keyword banks for the selected domains (typically ≤ 4 banks ≤ 200 terms) |
| 4. Refinement Q&A | rule-based | matches against `keyword_mapping.unmapped_terms` + `contract_resolution.missing/ambiguities` |
| 5. Contract resolution | **never LLM** | `resolve.py`'s mode-driven resolver against the live registries |

Two LLM calls per session, not one big stew. Each prompt is bounded:
stage 1 gets the human text, stage 3 gets the decomposition + the
relevant keyword banks (not the entire vocabulary). This caps token
usage and bounds the model's freedom — by stage 3 it can only emit
terms from a closed list.

---

## 2. The vocabulary graph — four layers

```
       Layer 0   DOMAINS                      (≤ 12 entries, controlled menu)
                 e.g. genetics, relatedness, inheritance, popgen,
                      structural_variation, annotation, qc, …
                          │
                          │  many-to-many (a concept can sit in multiple domains)
                          ▼
       Layer 1   CONCEPTS                     (per-domain bank; ~ 20–80 terms each)
                 e.g. Mendelian, pedigree, theta, IBS0, kinship, FST,
                      piN/piS, ROH, …
                          │
                          │  resolves_to
                          ▼
       Layer 2   REGISTRY-VOCAB TARGETS       (controlled across the system)
                 e.g. analysis_id=ngsrelate
                      entity_type=variant_site
                      set_filter=karyotype_HOM_INV
                      operation_type=thin_by_distance
                          │
                          │  found in (per workspace)
                          ▼
       Layer 3   REGISTRY INSTANCES           (the actual rows on this machine)
                 e.g. sample_set_id=samples_226_v1
                      interval_set_id=inv_LG28_INV_001_v1
                      module_name=ngsrelate_pairwise_v2
```

### Why four layers, not three or five

- **Layer 0 (domains)** exists to cap stage 3's vocabulary. Without it,
  stage 3 sees everything; with it, stage 3 sees ≤ 4 banks. This is the
  single most important constraint on LLM hallucination.
- **Layer 1 (concepts)** is where most of the keyword TSV rows live.
  This is the "Mendelian → analysis_id=mendelian" map.
- **Layer 2 (registry-vocab targets)** is the controlled enum the
  rest of the system uses (`entity_type`, `analysis_id`, `operation_type`,
  `set_filter` predicates, etc.). It is closed and stable; you don't add to
  it without bumping a schema version.
- **Layer 3 (instances)** is the per-workspace state — the actual
  `sample_set_id`s, `interval_set_id`s registered today. Stage 5 picks
  these via the existing `resolve.py` policies.

Without layer 2, the LLM would map directly from human words to your
specific `samples_226_v1` row — too brittle, would break the moment you
rename a set. Layer 2 buffers the mapping.

### Graph edges (TSV-encoded; reproducibly readable)

Five edge kinds, all in `vocabulary/edges.tsv`:

| Edge kind | From | To | Meaning |
|---|---|---|---|
| `alias` | term (string) | term (string) | "trio" is an alias of "trio_check" |
| `is_a` | concept | concept | "Mendelian" is_a "inheritance_test" |
| `belongs_to` | concept | domain | "FST" belongs_to "popgen" AND "popgen.differentiation" |
| `resolves_to` | concept | (kind, target) | "Mendelian" → (analysis_id, "mendelian") |
| `requires` | concept | concept | "pedigree-based GWAS" requires "pedigree" |

`alias` is one-directional but the matcher in stage 3 traverses both
directions. `is_a` lets stage 4 ask "did you mean the broader concept?"
when stage 3's match is ambiguous.

The graph is **persisted as TSVs** — flat, hand-editable, version-controlled —
not as a runtime DB. A small loader in `lib/vocabulary.py` (future PR)
reads the TSVs into an in-memory graph for the matcher.

---

## 3. The keyword banks (TSV-encoded vocabulary)

One TSV file per **domain** under `toolkit_registries/vocabulary/keywords/`:

```
toolkit_registries/vocabulary/
├── README.md                              (this layer's intro)
├── domains.tsv                            (Layer 0: the controlled menu of domains)
├── edges.tsv                              (graph edges across domains/concepts)
└── keywords/
    ├── inheritance.tsv
    ├── relatedness.tsv
    ├── popgen.tsv
    ├── structural_variation.tsv
    ├── annotation.tsv
    ├── population_history.tsv
    ├── qc.tsv
    └── sample_filtering.tsv
```

### One row, one term

```
term            level      maps_to_kind     maps_to                  aliases                                   notes
mendelian       concept    analysis_id      mendelian                mendel,inheritance_test,trio_check         per-trio inheritance check
pedigree        concept    analysis_id      ngspedigree              ped,family_tree                           pedigree reconstruction
trio            keyword    entity_type      pedigree_trio                                                      a parent–parent–offspring triple
relatedness     concept    analysis_id      ngsrelate                kinship                                    pairwise relatedness coefficient
theta           concept    metric           theta                                                              pairwise relatedness coefficient (ngsRelate column)
karyotype       concept    entity_type      group_definition         karyotype_class                            HOM_REF / HET / HOM_INV class
HOM_INV         keyword    set_filter       karyotype:HOM_INV                                                  carrier of two inverted alleles
old_families    keyword    set_filter       population_history:old_lineage   ancient_lineages                  filter samples by ROH/heterozygosity/relatedness signature
inversion       concept    entity_type      inversion_candidate      inv,inv_candidate                          a putative inversion call
chromosome      concept    entity_type      chromosome               chrom,chr,linkage_group
chr12           keyword    set_id_pattern   *LG12*                                                            chrom-12 family of intervals; resolver will look for matches
```

Columns (pinned by `keyword_bank_row_v1.schema.json`):

| Column | Purpose |
|---|---|
| `term`         | The canonical surface word. Lowercase preferred. |
| `level`        | `keyword` (literal surface), `concept` (controlled head), `registry_entry` (points at a specific id) |
| `maps_to_kind` | One of: `entity_type`, `analysis_id`, `set_filter`, `set_id_pattern`, `operation_type`, `metric`, `concept` |
| `maps_to`      | The target id / pattern. For `set_filter` use `<dimension>:<value>` (e.g. `karyotype:HOM_INV`) |
| `aliases`      | Comma-separated alternates. The matcher queries this column too. |
| `notes`        | Free-form for documentation. |

### Why TSV (not RDF / OWL / Neo4j)

Tradeoffs:

- ✓ Human-editable in any editor; `git diff` is meaningful.
- ✓ Trivial to parse from any language (Python, JS, R, shell).
- ✓ Per-domain partitioning means you only load what you need.
- ✓ Versioned. Each row's effective semantics are pinned by the row schema (`keyword_bank_row_v1.schema.json`).
- ✗ No transitive closure or graph-walks for free — the matcher computes them.

This is correct. A real KG would be overkill for a vocabulary of ≤
2000 terms. If it grows past 5000, we revisit.

---

## 4. Stage outputs — 5 JSON schemas

Each stage's output is a structured JSON document. Schemas live in
`toolkit_registries/schemas/registry_schemas/funnel_stage_*.schema.json`.

### Stage 1 — `funnel_stage_1_decomposition_v1`

```jsonc
{
  "stage":        "1_decomposition",
  "raw_request":  "Find Mendelian inversions on chromosome 12 but not from old families",
  "goal":         "identify inversion candidates with Mendelian-compatible inheritance, restricted by family origin",
  "targets":      ["chromosome 12", "inversion candidates"],
  "exclusions":   ["old families"],
  "concepts":     ["inheritance testing", "structural variation",
                   "family / pedigree structure", "population history"],
  "vague_terms":  ["old families", "Mendelian"]
}
```

`vague_terms` is the handoff to stage 4 — terms that need disambiguation.

### Stage 2 — `funnel_stage_2_domain_selection_v1`

```jsonc
{
  "stage": "2_domain_selection",
  "selected_domains": ["inheritance", "structural_variation",
                        "population_history", "sample_filtering"],
  "rationale": {
    "inheritance":          "trigger: 'Mendelian'",
    "structural_variation": "trigger: 'inversions'",
    "population_history":   "trigger: 'old families'",
    "sample_filtering":     "trigger: 'not from'"
  }
}
```

The selected domains drive which keyword banks are loaded for stage 3.

### Stage 3 — `funnel_stage_3_keyword_mapping_v1`

```jsonc
{
  "stage": "3_keyword_mapping",
  "mapped_terms": [
    { "source_term": "Mendelian",     "role": "test_type",
      "maps_to_kind": "analysis_id",  "maps_to": "mendelian",
      "domain": "inheritance",  "confidence": "high" },

    { "source_term": "inversions",    "role": "target_entity",
      "maps_to_kind": "entity_type",  "maps_to": "inversion_candidate",
      "domain": "structural_variation", "confidence": "high" },

    { "source_term": "chromosome 12", "role": "target_interval",
      "maps_to_kind": "set_id_pattern", "maps_to": "*LG12*",
      "domain": "structural_variation", "confidence": "medium" },

    { "source_term": "old families",  "role": "exclusion_basis",
      "maps_to_kind": "set_filter",   "maps_to": "population_history:old_lineage",
      "domain": "population_history", "confidence": "medium" }
  ],
  "unmapped_terms": []
}
```

Confidence values trigger stage 4 differently:
- **high** — accepted as-is, no question.
- **medium** — surfaces in a "did I get this right?" confirmation card.
- **low** — surfaces with multiple candidates the user picks from.

### Stage 4 — `funnel_stage_4_refinement_v1`

Zero or more rounds; the funnel loops here until everything resolves.

```jsonc
{
  "stage": "4_refinement",
  "round": 1,
  "questions": [
    {
      "question_id":   "q_chr12_pattern",
      "kind":          "pick_one",
      "prompt":        "Which interval scope for chromosome 12?",
      "context":       "Stage 3 mapped 'chromosome 12' to pattern '*LG12*' but multiple intervals match.",
      "options": [
        { "id": "C_gar_LG12_full_v1",          "label": "Full chromosome (34.5 Mb)" },
        { "id": "inv_LG12_INV_001_v1",         "label": "A specific inversion candidate on LG12" },
        { "id": "windows_LG12_50kb_v1",        "label": "50 kb tiling windows" }
      ]
    },
    {
      "question_id":   "q_old_family_threshold",
      "kind":          "free_text",
      "prompt":        "By 'old families' do you mean: a specific population_history class id, or a numeric threshold (e.g. ROH > 0.10)?",
      "context":       "Stage 3's set_filter 'population_history:old_lineage' is conceptual; need a concrete predicate."
    }
  ]
}
```

Question kinds (locked vocabulary):

| `kind` | UI shape |
|---|---|
| `pick_one`        | radio buttons; `options[]` required |
| `pick_multiple`   | checkboxes; `options[]` required |
| `free_text`       | text input; optional `pattern` / `placeholder` |
| `confirm`         | "Yes / Skip / Cancel"; `default: yes` |

User answers are captured as `funnel_stage_4_refinement_answer_v1`:

```jsonc
{
  "stage":  "4_refinement_answer",
  "round":  1,
  "answers": {
    "q_chr12_pattern":         "inv_LG12_INV_001_v1",
    "q_old_family_threshold":  "ROH > 0.10 AND heterozygosity < 0.15"
  }
}
```

Answers fold back into `keyword_mapping` (the resolver re-runs with
the disambiguated values; if more ambiguity surfaces, another round).
**Maximum 3 rounds before the funnel hands off to a "I cannot resolve
this — escalate" state.** This guards against infinite Q&A loops.

### Stage 5 — `funnel_stage_5_contract_resolution_v1`

```jsonc
{
  "stage": "5_contract_resolution",
  "plan": [
    {
      "step":              1,
      "analysis_id":       "ngsrelate",
      "mode":              "per_candidate",
      "sample_set_id":     "samples_226_minus_old_families_v1",
      "interval_set_id":   "inv_LG12_INV_001_v1",
      "site_set_id":       "sites_inv_LG12_INV_001_v1",
      "input_value_id":    "beagle_inv_LG12_INV_001_v1",
      "input_artifact_layer_ids": [],
      "params":            { "F_unknown": -1, "p": "ALL" },
      "status":            "todo",
      "missing_inputs":    []
    },
    {
      "step":              2,
      "analysis_id":       "ngspedigree",
      "mode":              "global",
      "status":            "todo",
      "input_result_id":   "<future: step 1 produced_layers[0]>"
    },
    {
      "step":              3,
      "analysis_id":       "mendelian",
      "mode":              "per_candidate",
      "status":            "todo",
      "input_result_id":   "<future: step 2 produced_layers[0]>"
    }
  ],
  "spawnable": [
    {
      "kind":          "set",
      "proposed_id":   "samples_226_minus_old_families_v1",
      "rationale":     "user requested 'not from old families'; derive by filtering samples_226_v1 against population_history:old_lineage",
      "proposal":      { /* skeleton set_v1 JSON */ }
    }
  ],
  "missing":     [],
  "ambiguities": []
}
```

This is the handoff to the action endpoint: `POST /api/actions` once
per `plan[]` step.

---

## 5. Implementation roadmap

Three phases. Each is independently shippable.

### Phase A — vocabulary (this PR's scope)

- `vocabulary/domains.tsv` — controlled list of Layer-0 domains.
- `vocabulary/keywords/*.tsv` — one bank per domain. Three starter banks
  ship here (`inheritance`, `relatedness`, `structural_variation`); the
  rest are TODO with empty skeletons.
- `vocabulary/edges.tsv` — concept-to-concept edges (aliases / is_a /
  requires).
- The five stage schemas in `toolkit_registries/schemas/registry_schemas/funnel_stage_*.schema.json`.
- A `keyword_bank_row_v1.schema.json` pinning the TSV columns.

**No code.** Pure design + data files.

### Phase B — deterministic resolver (later PR)

`lib/funnel.py`:
- `decompose(raw)` — calls the LLM (stage 1).
- `select_domains(decomp)` — rule-based by default (matches `decomp.concepts` against `domains.tsv.tags`); LLM-fallback only if rules ambiguous.
- `map_keywords(decomp, banks)` — calls the LLM (stage 2) with only the selected banks in the prompt.
- `refine(state)` — purely rule-based; reads `keyword_mapping.unmapped_terms` + a dry `resolve_step()` to find ambiguities, emits a `refinement_v1`.
- `resolve_contracts(state)` — reuses the existing `relatedness/scripts/resolve.py` and `lib/set_algebra.py` modules.

Each function consumes stage-N JSON, emits stage-(N+1) JSON. State is
the concatenated JSON envelope. Replayable from any stage.

### Phase C — UI (later PR)

Page 1 (`conversation.html`) becomes:
- A text box ("What's your research question?").
- A live, streaming render of the five stage panels, each as a card.
- Stage 4 questions appear inline; answers flow back into the state.
- Final stage 5 panel shows the proposed plan; "Submit to /api/actions"
  button submits each step.

The page is read-only without LLM keys configured — it can replay
saved sessions from `<workspace>/funnel_sessions/<session_id>.json`.

---

## 6. Prompts (Stage 1 and Stage 3)

The two LLM calls. **Locked prompts** below so different model versions
behave consistently across sessions. Update only with a `schema_version`
bump.

### Stage 1 prompt (decomposition)

System:

> You are a careful research librarian. Your job is to take a researcher's
> free-text request and produce a clean, structured decomposition. You do
> NOT pick files, IDs, or specific analyses — your job is to make the
> request less ambiguous, not to answer it. Use `unknown` for fields you
> cannot fill.
>
> Output JSON that matches `funnel_stage_1_decomposition_v1`. Do not
> output anything else. If the request is too vague to decompose at all,
> emit `{"stage": "1_decomposition", "raw_request": <input>, "goal": "unknown", "vague_terms": [<all words>]}`.

User: just the raw request text.

### Stage 3 prompt (keyword mapping)

System:

> You are a keyword mapper. You will receive:
>
>   1. A decomposition JSON (stage 1 output).
>   2. A list of one or more keyword banks (TSVs) — these are the ONLY
>      controlled vocabulary you may use.
>
> Map every concept and target from the decomposition to rows in those
> banks. For each mapping include `source_term`, `role`, `maps_to_kind`,
> `maps_to`, `domain`, and `confidence` (`high` / `medium` / `low`).
> Unmappable terms go in `unmapped_terms[]`.
>
> Rules:
>   - **maps_to MUST come from the banks**, exactly. No substitutions, no
>     invented ids. If nothing in the banks fits, put the term in
>     `unmapped_terms[]`.
>   - `confidence: low` is acceptable. The downstream stage uses it to
>     ask the user.
>   - Do not infer the user wants more than what they said. If they only
>     mention chromosome 12, do NOT also map "genome-wide".
>
> Output JSON matching `funnel_stage_3_keyword_mapping_v1`. Nothing else.

User: `{ "decomposition": {...}, "banks": [{...tsv rows...}] }`

---

## 7. Provider-agnostic

The funnel is provider-agnostic. The two LLM calls are HTTP requests
with a JSON body and a JSON-schema-constrained response. Any model that
supports structured output (Claude, OpenAI, Gemini, local Llama with
constrained decoding) can drive it.

Implementation note: when the chosen provider supports **JSON schema
mode** natively (constrained decoding), use it for both stages — the
five stage schemas are already in
`toolkit_registries/schemas/registry_schemas/`. Otherwise prompt-only
with a final `json.loads` + schema validation; if validation fails,
retry once with the validation error appended to the prompt.

---

## 8. Worked example end-to-end

Input:

> "Find Mendelian inversions on chromosome 12 but not from old families."

**Stage 1 output** (decomposition):

```jsonc
{
  "stage": "1_decomposition",
  "raw_request": "Find Mendelian inversions on chromosome 12 but not from old families.",
  "goal": "identify inversion candidates with Mendelian-compatible inheritance, restricted by family origin",
  "targets":    ["chromosome 12", "inversion candidates"],
  "exclusions": ["old families"],
  "concepts":   ["inheritance testing", "structural variation",
                  "family / pedigree structure", "population history"],
  "vague_terms": ["old families"]
}
```

**Stage 2 output** (domain selection):

```jsonc
{
  "stage": "2_domain_selection",
  "selected_domains": ["inheritance", "structural_variation",
                        "population_history", "sample_filtering"]
}
```

**Stage 3 output** (keyword mapping; ONLY these four banks loaded):

```jsonc
{
  "stage": "3_keyword_mapping",
  "mapped_terms": [
    { "source_term": "Mendelian",     "maps_to_kind": "analysis_id",
      "maps_to": "mendelian",         "confidence": "high" },
    { "source_term": "inversions",    "maps_to_kind": "entity_type",
      "maps_to": "inversion_candidate", "confidence": "high" },
    { "source_term": "chromosome 12", "maps_to_kind": "set_id_pattern",
      "maps_to": "*LG12*",            "confidence": "medium" },
    { "source_term": "old families",  "maps_to_kind": "set_filter",
      "maps_to": "population_history:old_lineage", "confidence": "medium" }
  ]
}
```

**Stage 4 — refinement round 1:**

```jsonc
{
  "stage": "4_refinement", "round": 1,
  "questions": [
    {
      "question_id": "q_chr12_pattern",
      "kind": "pick_one",
      "prompt": "Which interval scope for chromosome 12?",
      "options": [
        { "id": "C_gar_LG12_full_v1",  "label": "Full chromosome (34.5 Mb)" },
        { "id": "inv_LG12_INV_001_v1", "label": "Specific inversion candidate" }
      ]
    },
    {
      "question_id": "q_old_family_threshold",
      "kind": "free_text",
      "prompt": "By 'old families' do you mean a specific population_history class id, or a numeric threshold (e.g. ROH > 0.10)?"
    }
  ]
}
```

User answers: `q_chr12_pattern = inv_LG12_INV_001_v1`,
`q_old_family_threshold = ROH > 0.10`.

**Stage 5 output** (contract resolution):

Three-step plan: `ngsrelate / per_candidate → ngspedigree / global →
mendelian / per_candidate`, all scoped to
`samples_226_minus_old_families_v1` (a derived set the resolver
proposes in `spawnable[]`) on `inv_LG12_INV_001_v1`.

The plan goes to the action endpoint; PR #5's dispatcher executes it;
results flow back into the registries.

The original *"Find Mendelian inversions on chromosome 12 but not from
old families"* has, after one Q&A round, become a deterministic,
reproducible chain of registry contracts.

---

## 9. What this design refuses to do

- **Free-text answers in stage 5.** Stage 5 is deterministic; if it
  can't resolve, stage 4 fires again with a more pointed question.
- **Cross-domain leaks in stage 3.** The prompt only ever shows the
  banks for the selected domains. No "and while you're at it, here are
  all 2000 terms" prompts.
- **Action execution.** This page never runs anything. It produces
  action_manifests that `POST /api/actions` runs.
- **Persistent learning from user corrections.** Each session is
  independent; corrections are NOT folded back into the banks
  automatically (that would invalidate prior sessions). Bank updates
  are a deliberate human action, version-bumped, reviewed.
- **Free-form prompt engineering.** Both LLM prompts are locked in
  this spec; changes require a schema version bump.

---

## 10. Reading order for a contributor

1. **This file** — the contract.
2. `vocabulary/README.md` + `vocabulary/domains.tsv` — Layer 0.
3. One starter bank: `vocabulary/keywords/inheritance.tsv` — Layer 1 example.
4. `vocabulary/edges.tsv` — the graph edges.
5. The five stage schemas in `schemas/registry_schemas/funnel_stage_*.schema.json`.
6. `PIPELINE_FLOW.md` (PR #2) — where stage 5's action_manifests go.
7. `relatedness/scripts/resolve.py` (PR #2) — the deterministic
   resolver stage 5 reuses.
