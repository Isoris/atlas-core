#!/usr/bin/env bash
# run_bp_atlas_LAPTOP.sh -- BP_ATLAS on the laptop, sequential & watchable.
# Legacy all-vs-all pairing (from STEP_BP1) but divergence-TIERED identity so
# each pair aligns at a -p it can clear; deep-outgroup pairs auto-skip.
# ONE pair at a time (peak RAM = 2 genomes). Resumable (skips done PAFs).
#
# Run from MODULE_BPATLAS_crossspecies/scripts/ AFTER editing manifest paths
# to point at the local genomes. Watch the per-pair record counts scroll.
set -uo pipefail

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$MODULE_DIR/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/results_bpatlas"
LOGS_DIR="${ROOT_DIR}/logs"
mkdir -p "$LOGS_DIR" "$RESULTS_DIR"

# --- config for the cross-species LAPTOP run ---
export MANIFEST="${MANIFEST:-$MODULE_DIR/haplotype_manifest_CROSSSPECIES.tsv}"
export ANCHOR="${ANCHOR:-Cgar,Cmac}"        # reciprocity: anchor on both
# CPUS: wfmash -t threads. Peak RAM is driven by the TARGET genome index, NOT
# by thread count, so 2-3 threads is plenty on a 5GB laptop and barely changes
# memory. Default 2 leaves a core free for the OS while a pair aligns.
CPUS="${CPUS:-2}"
STAGE_END="${STAGE_END:-3}"                  # BP1->BP2->BP3->BP3c (stop before BP4 pop/BP5 figs)
# FOCAL_ONLY=1 keeps only pairs whose QUERY is Cgar or Cmac (~30 pairs instead
# of ~240). This is the handoff's "FASTER ALTERNATIVE" and the recommended
# default for a Clarias-focused manuscript on a weak laptop — it loses nothing
# for the headline (LG27/LG23) and is hours, not days. Set FOCAL_ONLY=0 for the
# full all-vs-all grind.
FOCAL_ONLY="${FOCAL_ONLY:-1}"
# SKIP_QUERIES: species codes to NOT run as QUERY (still used as targets).
# NOTE: this does NOT lower peak RAM in focal-only mode — the focal query is
# always Cgar/Cmac, so a skipped species would only have been a target anyway.
# Kept for the all-vs-all case where a big genome would otherwise be a query.
SKIP_QUERIES="${SKIP_QUERIES:-}"
# SKIP_TARGETS: species codes to NOT use as the wfmash TARGET. *** THIS is the
# real RAM lever ***: wfmash indexes the target (first positional arg), so peak
# memory tracks the target genome size. On a 5GB laptop the >1GB genomes
# (N_graeffei 2.4GB, P_lineatus 1.35GB, C_apus 1.2GB) risk OOM when indexed.
# Default skips all three; run those targets on LANTA (SLURM path) or set
# SKIP_TARGETS="" once you've confirmed your free RAM. Their breakpoints are a
# CONFIRMATION layer only — dropping them does not change the LG27/LG23 headline.
SKIP_TARGETS="${SKIP_TARGETS:-Ngra,Plin,Capus}"
cd "$ROOT_DIR"

echo "=== BP_ATLAS LAPTOP run (sequential, tiered) $(date) ==="
echo "MANIFEST: $MANIFEST"
echo "ANCHOR:   $ANCHOR   STAGE_END: $STAGE_END   wfmash -t $CPUS"
echo "FOCAL_ONLY: $FOCAL_ONLY   SKIP_QUERIES: ${SKIP_QUERIES:-<none>}   SKIP_TARGETS: ${SKIP_TARGETS:-<none>}"

# --- Stage 1: build pairs, run each sequentially ---
echo ""; echo "--- Stage 1: build pairs ---"
bash "$MODULE_DIR/STEP_BP1_pairwise_wfmash.sh" --build-pairs-only
PAIRS_FULL="$RESULTS_DIR/01_pairs/pairs.tsv"

# Apply laptop subsetting (focal-only and/or query-species skips) to a derived
# pairs file. STEP_BP1's array index reads from pairs.tsv by pair_idx, so we
# subset by REWRITING pairs.tsv in place (keeping the header) and stash the
# full list as pairs.full.tsv for provenance. pair_idx values stay aligned
# because we filter on the SAME column 1 the array task selects on.
if [[ "$FOCAL_ONLY" == "1" || -n "$SKIP_QUERIES" || -n "$SKIP_TARGETS" ]]; then
  cp "$PAIRS_FULL" "$RESULTS_DIR/01_pairs/pairs.full.tsv"
  awk -F'\t' -v focal="$FOCAL_ONLY" -v skipq="$SKIP_QUERIES" -v skipt="$SKIP_TARGETS" '
    BEGIN{
      n=split(skipq, Q, ","); for(i=1;i<=n;i++) if(Q[i]!="") skipQ[Q[i]]=1
      m=split(skipt, T, ","); for(i=1;i<=m;i++) if(T[i]!="") skipT[T[i]]=1
    }
    NR==1{ print; next }
    {
      qsp=$4; tsp=$8
      if (focal=="1" && qsp!="Cgar" && qsp!="Cmac") next
      if (qsp in skipQ) next
      if (tsp in skipT) next        # RAM guard: drop pairs whose TARGET is too big to index
      print
    }' "$RESULTS_DIR/01_pairs/pairs.full.tsv" > "$PAIRS_FULL"
  echo "  subset applied (focal_only=$FOCAL_ONLY, skip_queries=${SKIP_QUERIES:-none}, skip_targets=${SKIP_TARGETS:-none})"
fi
PAIRS="$PAIRS_FULL"
# Build the explicit list of pair_idx values to run (column 1), since after
# subsetting the indices are no longer a contiguous 0..N-1 range.
mapfile -t RUN_IDX < <(awk -F'\t' 'NR>1{print $1}' "$PAIRS")
NP=${#RUN_IDX[@]}
echo "  $NP pairs to run (deep-outgroup pairs will self-skip inside STEP_BP1)"

pos=0
for idx in "${RUN_IDX[@]}"; do
  pid=$(awk -F'\t' -v i="$idx" 'NR>1&&$1==i{print $2}' "$PAIRS")
  a="$RESULTS_DIR/02_paf_passA/${pid}.paf"; b="$RESULTS_DIR/02_paf_passB/${pid}.paf"
  am="$RESULTS_DIR/02_paf_passA/${pid}.meta.tsv"
  # A pair is "done" if BOTH passes produced records (normal case) OR if BP1
  # wrote a meta sidecar with a deep-outgroup SKIP (empty PAFs are EXPECTED
  # there, so the old `-s` test wrongly re-ran skip pairs every resume).
  if [[ -s "$a" && -s "$b" ]]; then echo "  [$idx] $pid done, skip"; continue; fi
  if [[ -f "$am" ]] && awk -F'\t' 'NR==2{exit !($9==0 && $10==0)}' "$am"; then
    echo "  [$idx] $pid deep-outgroup skip (already recorded), skip"; continue
  fi
  pos=$((pos + 1))
  echo "  [$pos/$NP] (pair_idx $idx) $pid  $(date +%H:%M)"
  SLURM_ARRAY_TASK_ID="$idx" SLURM_CPUS_PER_TASK="$CPUS" \
    bash "$MODULE_DIR/STEP_BP1_pairwise_wfmash.sh" \
    > "$LOGS_DIR/bp_pair${idx}.out" 2> "$LOGS_DIR/bp_pair${idx}.err" \
    || echo "    WARN rc=$? (see logs/bp_pair${idx}.err)"
  # show the record counts so you can watch which pairs aligned
  grep -h 'records ->' "$LOGS_DIR/bp_pair${idx}.out" 2>/dev/null | sed 's/^/    /' || true
done

# --- Stage 2: BP2 over all PAFs ---
# --min-mapq 1 is REQUIRED: STEP_BP1 feeds wfmash --approx-mapping PAFs whose
# MAPQ is 1-5, not 40 like minimap2. Without this, BP2's old default (5)
# silently dropped every block and produced 0 breakpoints (the exact failure
# diagnosed in chat 1b4d8e12). Keep it explicit here so the laptop run is
# correct regardless of the script default.
echo ""; echo "--- Stage 2: BP2 call breakpoints (--min-mapq 1 for wfmash) ---"
python3 "$MODULE_DIR/STEP_BP2_call_breakpoints.py" \
  --paf-dir "$RESULTS_DIR/02_paf_passA" \
  --out "$RESULTS_DIR/03_breakpoints" --min-block-bp 50000 --min-mapq 1 \
  2>&1 | tail -5

# --- Stage 3: BP3 zones per anchor + BP3c reciprocity ---
# Wire the Pass B (-s 500k) backbone in via --passB-paf-dir so each zone gets
# a real backbone_support flag (yes/partial/no) instead of "n/a". Zones whose
# Pass-A signal does not sit on a coarse synteny chain are forced low-confidence
# — this is the repeat-artifact guard the two-pass design exists for.
echo ""; echo "--- Stage 3: BP3 zones (per anchor, Pass B backbone wired) ---"
PASSB_DIR="$RESULTS_DIR/02_paf_passB"
IFS=',' read -ra ANCHORS <<< "$ANCHOR"
for A in "${ANCHORS[@]}"; do
  OUT="$RESULTS_DIR/03_breakpoints/anchor_${A}"; mkdir -p "$OUT"
  python3 "$MODULE_DIR/STEP_BP3_cluster_zones.py" \
    --raw-bp "$RESULTS_DIR/03_breakpoints/breakpoints_raw.tsv" \
    --anchor-species "$A" --out "$OUT" \
    --passB-paf-dir "$PASSB_DIR" 2>&1 | tail -3
done
CG="$RESULTS_DIR/03_breakpoints/anchor_Cgar"; CM="$RESULTS_DIR/03_breakpoints/anchor_Cmac"
if [[ -f "$CG/breakpoint_zones.tsv" && -f "$CM/breakpoint_zones.tsv" ]]; then
  echo ""; echo "--- Stage 3c: reciprocity (Cgar <-> Cmac) ---"
  python3 "$MODULE_DIR/STEP_BP3c_reciprocity.py" \
    --cgar-dir "$CG" --cmac-dir "$CM" \
    --out "$RESULTS_DIR/03_breakpoints/reciprocity" --zone-kinds inversion,translocation 2>&1 | tail -5
fi
echo ""; echo "=== done $(date). Zones + reciprocity in $RESULTS_DIR/03_breakpoints/ ==="
echo "BP4 (226-cohort overlap) + BP5 figures: NEXT CHATS (cohort/figure boundary)."
