# Atlas input data layout

Single source-of-truth for **which on-disk files each atlas reads**, so raw
analysis outputs can be organized into the right slots. Generated from each
atlas's `registries/data/{layers,files}.registry.json` on 2026-05-29.

To scaffold the empty tree: `bash atlas-core/build/setup_local_dirs.sh`.
Root → absolute path mapping lives in `master_config.yaml` (`roots:` block).

---

## Two data models

| Model | Meaning | Atlases |
|---|---|---|
| **A — results root** | Layer declares `root` + `path_under_root`; file lives under `/mnt/e/results_<atlas>/…` and is served by the unified server. **These need files organized in.** | inversion, diversity, heterozygosity, genome, cross-species, evolution, popstats, pods, loads |
| **B — committed `data/`** | Layer declares an atlas-relative `path` (`data/…json`); the file is **committed in the atlas repo**, carved from upstream. No results root needed. | population, relatedness, meiosis |

Other layer sources that need **no input file**:
- `source: operation` — computed server-side on request (output cached, not pre-staged).
- `source: analysis` — computed in-browser.

Legend below: **[disabled]** = layer declared but the producer step hasn't shipped (empty on disk by design); **[auto]** = server auto-indexes filenames under the root (no fixed pattern).

Naming: results roots are `results_<atlas>` (underscore). The inversion tree is the historical plural `results_inversions`. `{…}` are runtime templates (chrom / sample / candidate / K / cohort) the producer expands.

---

## Model A — atlases that read a results root

### inversion → `/mnt/e/results_inversions/`
Auto-indexed precomp roots (per-chrom atlas JSONs, discovered via `/api/precomp_index`):

| root | path under root |
|---|---|
| `precomp_zblocks` | `local_PCA_MDS_z/09_atlas_json/` — `C_gar_LG{NN}.atlas.json` [auto] |
| `precomp_thetapi` | `local_PCA_MDS_theta_pi/04_atlas_json/C_gar_LG{NN}/C_gar_LG{NN}_phase2_theta.json` [auto] |
| `precomp_ghsl` | `local_PCA_MDS_GHSL/10_atlas_json/C_gar_LG{NN}/C_gar_LG{NN}_phase3_ghsl.json` [auto] |

Plus, consumed by **server operations** (not registry-resolved files): `beagle`,
`cohort_dosage`, `clair3_phased_ghsl`, `inversion_theta_pi_pestPG`. 7 `operation` +
4 `analysis` layers carry no input file. **23 layers read committed `data/…`** (Model B
within the atlas: cohort/, candidates/, regimes/, comparative/, arrangement_calls/) —
several `[disabled]` precomp/* placeholders.

### diversity → `/mnt/e/results_diversity/`

| root | path under root |
|---|---|
| `diversity_heterozygosity` | `04_summary/genomewide_heterozygosity.tsv` |
| | `02_sfs/{sample_id}.est.ml` |
| | `05_single_heterozygosity_boxplot/single_boxplot_input_dataframe.tsv` |
| | `05_ancestry_heterozygosity/tables/{kruskal,anova,pairwise_wilcox,pairwise_ttest,cluster_summary,summary,outliers_cluster,outliers_qmaxclass,q_correlations,q_linear_models,merged}_K{K}_{cohort}.tsv` |
| | `05_ancestry_heterozygosity/tables/whole_sample_outliers_{cohort}.tsv` |
| | `05_ancestry_heterozygosity/tables/{anova,kruskal,pairwise_ttest,pairwise_wilcox,q_correlations,q_linear_models}_results_all.tsv` |
| | `05_ancestry_heterozygosity/tables/{cluster_summary_all,cleaned_heterozygosity,cleaned_structure_labels,pruned81_samples,best_seed_metadata,all_outliers}.tsv` |
| `diversity_theta_pi` | `{sample_id}.win{win_bp}.step{step_bp}.pestPG` |
| | `{sample_id}.win{win_bp}.step{step_bp}.pestPG.arg` [disabled] |
| `diversity_saf_per_sample` | `{sample_id}.arg` (SAF binaries are NOT mirrored to E:) |
| `diversity_roh` | `per_sample/{sample_id}.roh.tsv` · `per_chrom/froh_per_sample_per_chrom.tsv` · `per_sample/length_class_bins.tsv` · `per_sample/{sample_id}.het_in_out_roh.tsv` — all [disabled] |
| `diversity_aggregated` | `samples_master.tsv` · `per_chromosome_master.tsv` · `naratora_pruned81_status.tsv` · `ngsf_hmm_convergence.tsv` · `kinship_summary.tsv` · `spearman_correlations.tsv` · `cohort_globals.json` — all [disabled] |

`{K}` ∈ `02`..`12` (zero-padded); `{cohort}` ∈ `all226`,`pruned81`. Also 5 committed
`data/*.json` payloads (texture/burden/roh-gene/divergence/msa) + 2 `operation` layers.

### heterozygosity → reads `/mnt/e/results_diversity/`, writes cache
Reads a subset of `diversity_heterozygosity` (`04_summary/genomewide_heterozygosity.tsv`,
`05_ancestry_heterozygosity/tables/merged_K{K}_{cohort}.tsv`, `kruskal_results_all.tsv`,
`single_boxplot_input_dataframe.tsv`, `02_sfs/{sample_id}.est.ml`). One `operation` layer
(`f_roh_h_plane_v1`) **writes** `heterozygosity_session` → `/mnt/e/atlas-cache/heterozygosity/sessions/f_roh_h_plane.tsv`.

### genome → `/mnt/e/results_genome/`

| root | path under root |
|---|---|
| `genome_assembly` | `assembly_stats.json` · `chromosome_map.json` · `centromere_telomere.json` |
| `genome_annotation` | `gene_track.gff` · `repeat_track.bed` · `te_hierarchy.json` · `variant_annotations.json` |
| `genome_conservation` | `conserved_elements.bed` |
| `genome_synteny` | `synteny_blocks.json` · `macrosynteny_orthologs.json` · `oxford/{a_id}_{b_id}.json` · `orthologs/{focal_id}.json` · `orthologs/pairs/{focal}_{nonfocal}.json` |

(`genome_te_density` root exists in config but no layer reads it yet.) Plus 6 committed
`data/comparative/*.json`.

### cross-species → `/mnt/e/results_cross_species/`

| root | path under root |
|---|---|
| `cross_species_manifests` (`00_manifests`) | `haplotype_manifest_{18sp,5hap}.tsv` |
| `cross_species_bp_atlas` (`01_bp_atlas`) | `passA/` · `passB/` · `breakpoints_raw.tsv` · `zones_{anchor}.tsv` · `reciprocity.tsv` · `reciprocity/reciprocity_table.tsv` · `atlas_data.json` · `atlas_paf_arcs.json` · `joint_candidates.tsv` · `pairs/{pair}/cs_breakpoints_v1.json` · `cs_pairs_v1.json` · `anchor_{anchor}/breakpoint_zones.tsv` · `breakpoint_junctions_v1.json` |
| `cross_species_consolidated` (`02_consolidated`) | `breakpoint_clusters.tsv` · `pairwise_summary_{focal}.tsv` · `verified_numbers_v1.json` · `supp_tables_v1.json` · `sweep/summary_*_*kb.tsv` |
| `cross_species_gene_order` (`03_gene_order`) | `synteny_{18sp,5sp}_breakpoints.tsv` · `oxford/{panel}_{focal_genome}.json` · `geneanchor/{panel}/geneanchor_breakpoints_v1.json` · `geneanchor_chunks_v1.json` · `geneanchor_pairs_v1.json` · `focal_busco_anchors_v1.json` |
| `cross_species_te` (`04_te`) ⭐new | `TE_data_figure1_toky_v2.tsv` · `combined_data_joined.tsv` · `te_gc.tsv` · `te_density_by_LG_species.tsv` · `breakpoint_te_cross/{focal_genome}/breakpoint_TEclass_enrichment_{focal_short}.tsv` · `…/breakpoint_resolution_{focal_short}.tsv` · `centromeres/centromeres_complete_{focal_short}.tsv` |
| `cross_species_mashmap` (`05_mashmap`) ⭐new | `fusion_fission_candidates_1to2.tsv` · `best_refs_per_query.tsv` · `pair/{request_id}.json` |
| `cross_species_breakpoint_genes` (`06_breakpoint_genes`) ⭐new | `breakpoint_gene_analysis_{focal_genome}.tsv` |
| `cross_species_phylogeny` (`07_phylogeny`) ⭐new | `busco_tree_v1__{alignment}.json` · `busco_qc_v1.json` · `busco_presence_absence_v1.json` |
| `cross_species_inventory` (`08_inventory`) ⭐new | `inventory_v1.json` |

### evolution → `/mnt/e/results_evolution/`

| root | path under root |
|---|---|
| `evolution_age_busco4d` (`01_age_busco_4d`) | `age_per_inversion.tsv` |
| `evolution_polarisation` (`02_polarisation`) | `synteny_vote/{candidate_id}.json` · `msa_stacked/{candidate_id}.json` |
| `evolution_haplotype_networks` (`03_haplotype_networks`) | `{candidate_id}.json` |
| `evolution_archaeology` (`04_archaeology`) | `{candidate_id}.json` |
| `evolution_orientation_diversity` (`05_orientation_diversity`) ⭐new | `{candidate_id}.json` |

(`inversion_summary_table` is served atlas-relative from `registries/data/`, not a results root.)

### popstats → `/mnt/e/results_popstats/`

| root | path under root |
|---|---|
| `popstats_groupwise` (`01_groupwise`) | `groupwise_stats.tsv` · `hobs_hexp_groupwise.tsv` |
| `popstats_ancestry` (`02_ancestry_painting`) | `per_window/{chrom}.json` · `per_fish/{candidate_id}.json` |

### pods → `/mnt/e/results_pods/`
All 3 layers are `operation` (server writes `<cache_key>`-named files): `simulations/` ·
`outlier_calls/` · `calibration/`.

### loads → `/mnt/e/results_loads/` ⭐new root
`load_per_individual.tsv` · `load_per_inversion.tsv`. Phase-0 stub (empty until pipeline ships).

---

## Model B — atlases that read committed `data/` (no results root)

These ship their inputs **inside the atlas repo**; nothing to organize on `/mnt/e/`.

- **population** → `data/{per_sample_stats[disabled],family_clusters,inversion_carriers,marker_controls,hatchery_health,qc/module_qc_summary}.json`, `data/ngsadmix/Q_K{k}.json`, `data/pcangsd/pca.json`, `data/ngsrelate/kinship_matrix.json`, `data/evaladmix/residuals.json[disabled]`. (Producer staging still lands in `results_population/` for the carve step.)
- **relatedness** → `data/relatedness/{pairwise_relationship_classification,family_hub_roster,per_chrom_qc,inversion_karyotypes,inversion_catalogue,ancestry_q}.tsv`, `cohort.beagle.gz`, `natora_prune.in`.
- **meiosis** → `data/crossovers/{candidate_id}.json`, `data/nco_gc/{candidate_id}.json`; 3 `operation` layers (`data/coincidence|effects|events/…`). Exports cross-atlas to inversion/evolution/genome.

---

## Status summary (2026-05-29)

- **Roots fixed today** (were referenced but undeclared → now in `master_config.yaml`): `cross_species_te`, `cross_species_mashmap`, `cross_species_breakpoint_genes`, `cross_species_phylogeny`, `cross_species_inventory`, `evolution_orientation_diversity`, `loads_results`.
- **On disk now:** `results_inversions/` + `results_diversity/` are populated. `results_cross_species/`, `results_evolution/`, `results_popstats/`, `results_pods/`, `results_loads/` are **absent** — run `setup_local_dirs.sh`, then move producer outputs in.
- **Producers** (where the raw outputs currently live, to be organized in): cross-species ← `catfish-synteny-toolkit` / `MODULE_SYNTENY_ATLAS`; diversity ← `catfish-diversity-analysis`; population ← `catfish-population-analysis`; inversion ← `catfish-inversion-analysis`.
