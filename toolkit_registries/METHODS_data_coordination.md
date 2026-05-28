# Methods — Registry-Mediated Coordination of Multi-Atlas Genomic Results

> **Provenance & scope.** This chapter documents the *coordination layer* of
> the analysis system — the data registry and the machinery that assembles
> per-object evidence across otherwise-independent analysis modules. It does
> **not** document the inversion-detection mathematics themselves (local-PCA
> eigenvalue scans, banding, concordance, dosage calling); those are
> implemented in a separate analysis repository and are out of scope here.
> Everything cited below is in the present repository and was read directly
> from source. File citations are given as `path:line` relative to the
> repository root so each rule can be checked against the implementation.
> Where a figure is reported, its provenance (real run vs. synthetic fixture)
> is stated explicitly; see §7.

---

## Abstract

A genomic study of chromosomal inversions in a 226-sample pure *Clarias
gariepinus* hatchery cohort distributes its computation across several
semi-independent analysis modules ("atlases") — inversion detection,
population statistics, evolutionary inference, relatedness, and comparative
genomics — each of which emits results about the *same* biological objects:
candidate inversions and long-range haplotype regimes. The analytical problem
this chapter addresses is not any single estimator but **coordination**:
guaranteeing that the scattered evidence about one object can be assembled
correctly, reproducibly, and without cross-cohort contamination. The system
adopts a *declarative registry* as its single source of truth and a strict
*broker, not executor* separation of concerns: it records what exists,
resolves the state of each result, plans what may run, and assembles evidence,
but never performs the analyses themselves. The central coordination
primitive is the **derived object** — a synthesised, addressable subject with
a stable identifier and a genomic interval, to which any module's results
attach through one of three declared join modes (foreign-key,
spatial-interval overlap, or chromosome scope). A generic harvester reads the
object declarations and assembles one aggregate record per instance. On the
synthetic validation fixtures shipped with the repository, the harvester
assembles the prototype LG28 candidate (`inv_LG28_INV_001`, interval
C_gar_LG28:1,200,000–8,400,000) from three evidence sources via two distinct
join modes; the same code path generalises without modification to a second
object kind (long-range haplotype regimes). The full registry passes a
26-step internal-consistency harness on every change.

---

## 1. Introduction

### 1.1 The coordination problem

Large genomic projects are rarely a single program. Detection, population
genetics, evolutionary modelling, pedigree/relatedness inference and
comparative genomics are developed and run as separate modules, often by
different people and on different schedules. Each module nonetheless produces
results *about the same things* — here, a small set of candidate inversions
and the haplotype regimes that span them. A candidate inversion is described
by its detection statistics, by per-window population-genetic contrasts
between karyotype groups, by an inferred age and polarity, by per-trio
Mendelian behaviour, and by its conservation across related taxa. These
descriptions live in different files, produced by different runs, in
different coordinate conventions.

The naïve way to assemble the complete picture of one candidate is to visit
each module's outputs in turn and join them by hand. This is slow, error-prone
and — critically for a study spanning multiple biological cohorts — unsafe:
nothing prevents a per-window statistic computed on one cohort from being
silently attributed to an object defined in another. The system documented
here replaces that manual join with a declarative, audited coordination layer.

### 1.2 Roadmap

§2 describes the registry that serves as the coordination substrate and the
three kinds of declaration it makes. §3 sets out the *broker, not executor*
principle and the resolve/plan/assemble tiers that follow from it. §4 defines
the derived-object model, the three join modes, and the harvester that is the
operational heart of result coordination. §5 documents cohort discipline as a
correctness invariant enforced by the registry rather than by convention. §6
covers reproducibility and the internal-consistency harness. §7 is the
honesty pass: what in this repository is genuinely wired and validated versus
what is scaffold or synthetic fixture.

---

## 2. The registry as coordination substrate

All shared knowledge is held as line-delimited JSON (JSONL) records under a
single registry directory (`toolkit_registries/relatedness/01_registry/`).
Each record is one declaration; one declaration per line; one file per kind of
declaration (analyses, modules, layers, atlases, cohorts, external databases,
addons, derived objects, and the run log). JSONL is chosen deliberately: it is
human-readable, line-diffable under version control, and append-friendly, so
the provenance of every declaration is visible in history.

The registry makes three logically distinct kinds of declaration, and keeping
them distinct is what lets the coordination layer reason about results without
running them:

1. **Schemas of capability** — what *can* be computed. Analyses and the
   compute modules that implement them, with their input and output contracts.
2. **Schemas of structure** — what *kinds of result* exist. Each result layer
   declares its entity type (e.g. a per-window statistic, a per-sample call, a
   per-candidate record) and where its rows live. The layer registry is the
   contract against which all downstream joins are checked.
3. **Schemas of synthesised subjects** — what *addressable objects* the system
   coordinates around. This is the derived-object registry (§4), the
   declaration that turns "rows in a file" into "evidence about an object."

The registry declares contracts; it never holds the bulk result data. Result
rows live in their own files and are referenced by the registry, keeping the
source of truth small, legible, and auditable.

---

## 3. Broker, not executor

The coordination layer is organised around a single architectural commitment:
**it never executes an analysis.** Its responsibilities are strictly to
*connect, resolve, plan, and assemble*; *running* an analysis is someone
else's job. This separation is stated in the dispatcher itself —
"the dispatcher never executes … this preserves the §refusals:
connect ≠ resolve ≠ run"
(`toolkit_registries/relatedness/lib/dispatcher.py:11-13`).

Four read-or-plan tiers follow from this commitment:

- **Resolution (the "librarian").** Given a result layer, determine its
  current state from the run log and the filesystem — present, absent,
  derivable — without computing anything
  (`toolkit_registries/relatedness/scripts/resolve_layer.py`).
- **Classification (the "manager").** Judge whether a research product or
  question is answerable from what currently exists, and what is missing if
  not (`toolkit_registries/relatedness/lib/manager.py`).
- **Planning (the "dispatcher").** When a computation is warranted, write an
  action manifest into a queue directory for an external runner to pick up; it
  "writes `action_manifest_v1` JSONs to `02_queue/`"
  (`toolkit_registries/relatedness/lib/dispatcher.py:74`) and stops there.
- **Composition.** A view-composition tier assembles which results are
  presented together from declarative rules. It is mentioned only for
  completeness; it computes nothing and is excluded from this chapter as a
  presentation concern.

The methodological payoff is that the coordination layer is *pure with respect
to the science*: it can be re-run, audited, and reasoned about freely because
it has no side effects on results. The actual estimators live in each atlas's
own compute module and are invoked only by the external runner.

---

## 4. The derived-object model

### 4.1 Objects, not rows

The unit of coordination is the **derived object**: a synthesised subject that
analyses produce evidence *about*, as opposed to the primary rows they
produce. A candidate inversion is the canonical example. It has a stable
identifier and a genomic interval, and its own rows live in a designated
*instance layer*; the derived-object registry only declares the *kind* and how
to gather evidence for it. Two kinds are declared in
`toolkit_registries/relatedness/01_registry/derived_objects.jsonl`: the
inversion `candidate` (identity key `candidate_id`, instance layer
`inversion_candidates`) and the `LRR_regime` long-range haplotype regime
(identity key `regime_id`, instance layer `long_range_haplotype_regime`).

Each declaration carries: an identity key, spatial keys (chromosome, start,
end), the instance layer where the object's own rows live, the lifecycle
states the object may occupy, and a `harvest` list naming each evidence source
and the join mode by which it attaches. The validator enforces that these
fields resolve — owning atlas exists, instance layer exists, identity keys and
lifecycle states are non-empty, and every harvest entry uses a known join mode
(`toolkit_registries/relatedness/scripts/check_derived_objects.py:41-70`).

### 4.2 The three join modes

Evidence attaches to an object by one of three declared modes; the
heterogeneity is intrinsic, because different estimators are keyed
differently. The harvester documents and implements all three
(`toolkit_registries/relatedness/lib/derived_object_harvester.py:9-14`):

1. **`direct_fk`** — the result rows carry the object's identifier as a
   foreign key; rows are selected where the key matches. (In the present
   implementation this mode is a declared extension point and performs no
   selection until a dedicated keyed file exists;
   `…/derived_object_harvester.py:118-131`. See §7.)

2. **`spatial_window`** — the result rows carry their own (chromosome, start,
   end), and a row attaches if and only if it lies on the object's chromosome
   and its interval overlaps the object's interval. Overlap is the standard
   half-open-interval test, `start ≤ object_end ∧ end ≥ object_start`
   (`…/derived_object_harvester.py:69-72`), applied after a chromosome-identity
   check that normalises naming conventions (e.g. `C_gar_LG28 → LG28`,
   `…/derived_object_harvester.py:58-61`). The selection logic is at
   `…/derived_object_harvester.py:138-145`.

3. **`chromosome`** — the result file is already scoped to one chromosome (one
   file per linkage group), so the whole table attaches to objects on that
   chromosome (`…/derived_object_harvester.py:146-147`). This is the correct
   mode for statistics that are not finer-grained than a chromosome, such as
   per-trio Mendelian summaries.

```
attach(result_row, object):
    direct_fk       : result_row[fk] == object.id
    spatial_window  : short(result_row.chrom) == short(object.chrom)
                      AND result_row.start <= object.end
                      AND result_row.end   >= object.start
    chromosome      : short(file.chrom)      == short(object.chrom)
```

### 4.3 The harvester

A single generic procedure realises the model. For an object kind it loads the
instance rows from the instance layer, and for each instance walks the
`harvest` list, resolving each evidence source's result file(s) from the run
log by matching the analysis type and the instance's chromosome short-name
against the recorded result path
(`toolkit_registries/relatedness/lib/derived_object_harvester.py:75-91`). It
then applies the declared join mode and emits one aggregate record per
instance, namespaced by object kind. The procedure is read-only and
cohort-safe by construction — "read-only, never mutates a registry, never
crosses cohort boundaries"
(`…/derived_object_harvester.py:20-22`) — because the instance row carries its
own cohort (§5).

Crucially, the harvester is *generic over the registry*: it contains no
object-specific logic. The second object kind (`LRR_regime`) is served by the
identical code path purely on the strength of its declaration in
`derived_objects.jsonl`, demonstrating that adding a coordinated object type is
a declaration, not a code change.

---

## 5. Cohort discipline as a correctness invariant

The study spans biologically distinct cohorts that must never be conflated.
The registry encodes them explicitly
(`toolkit_registries/relatedness/01_registry/cohorts.jsonl`):

- **`cgar_hatchery_226`** — the 226-sample pure *Clarias gariepinus* hatchery
  cohort that is the subject of this work. All per-sample inferences
  (karyotype calls, Mendelian QC, population statistics) are scoped here, and
  its population structure (`K`) reflects **hatchery broodline structure, not
  species admixture**.
- **`f1_hybrid_assembly`** — a single *C. gariepinus × C. macrocephalus* F1
  individual used only to produce the haplotype-resolved reference assembly (a
  separate study); its sole role here is to provide the coordinate frame.
- **`cmac_wild_future`** — a wild *C. macrocephalus* cohort reserved for future
  work, with no samples yet.

The invariant is precise: **coordinates may cross cohort boundaries; claims
may not.** A genomic interval defined on the shared assembly frame can be used
to query any cohort's results, but a statistic computed on one cohort may
never be reported as a property of an object owned by another. Because each
derived object's instance row carries its cohort, and because the harvester
never alters that field, the assembled aggregate inherits the object's cohort
unchanged — the safeguard is structural, not a matter of analyst vigilance.
This is the methodological reason coordination is mediated by the registry at
all: a hand join offers no such guarantee.

---

## 6. Reproducibility and internal-consistency validation

Three properties make the coordination layer reproducible. First, the
canonical representation is diffable text (JSONL), so every change to a
declaration is reviewable as a line diff. Second, the registry is closed under
a family of validators that reject malformed or dangling declarations — among
them checks that every analysis, plan, manuscript chunk, external-database
adapter, addon, and derived-object declaration resolves against the registry
it references
(`toolkit_registries/relatedness/scripts/check_*.py`). The derived-object
validator in particular rejects unknown join modes and unresolved instance
layers (`…/scripts/check_derived_objects.py:41-70`).

Third, all of this is bound into a single internal-consistency harness that
re-runs the validators, rebuilds the derived dependency graphs, and exercises
the harvester end-to-end on every change
(`toolkit_registries/scripts/smoke_all_stack.py`). At the time of writing the
harness comprises 26 steps and passes in full; two of those steps run the
harvester over both declared object kinds, so a regression in the join logic
or a dangling reference fails the harness rather than surfacing later as a
silently wrong aggregate. Extension is itself audited: new coordinated
capabilities are registered through an addon contract whose validator confirms
that every claimed registry row and shipped file actually exists
(`toolkit_registries/relatedness/scripts/check_addons.py`).

---

## 7. What is real versus scaffold in this repository

In keeping with an explicit honesty pass, the status of each component is
stated plainly.

**Wired and validated in this repository.** The registry and its declarations;
the resolve/classify/plan tiers; the full validator family and the 26-step
consistency harness; the derived-object model and the generic harvester, which
runs end-to-end over both declared object kinds; and the cohort declarations
and the structural cohort-safety of the harvester.

**Synthetic fixtures, not biological results.** The candidate instances used
to exercise the harvester are explicitly synthetic. The instance file
(`toolkit_registries/relatedness/02_sets/candidates/inversion_candidates.tsv`)
contains two rows, both annotated "synthetic": the prototype
`inv_LG28_INV_001` (C_gar_LG28:1,200,000–8,400,000) and the paired
`inv_LG01_INV_001`. The per-window and per-trio result tables they join
against are likewise small synthetic fixtures. Consequently the row counts the
harvester reports on these inputs are **demonstrations of the join logic, not
measurements of the cohort**, and must not be read as population-genetic
findings. Real detection and per-group statistics on the 226-sample hatchery
cohort are produced by the separate analysis repository and are out of scope
here.

**Scaffold / contract-only.** The `direct_fk` join mode is declared and
validated but is presently a no-op extension point in the harvester
(`…/derived_object_harvester.py:118-131`); foreign-key-keyed evidence layers
will attach once their files exist. The automatic karyotype caller shipped in
this repository is an explicitly labelled `v0` thresholding stub, not the
production model-based caller. Neither contributes results to §7's "validated"
list.

The distinction this section draws — *run on this data* versus *implemented
only* — is the same distinction the consistency harness enforces
mechanically: a declaration may exist and validate without yet having real
data behind it, and the coordination layer is careful never to present the
former as the latter.

---

_End of draft — Methods: registry-mediated coordination of multi-atlas results._
