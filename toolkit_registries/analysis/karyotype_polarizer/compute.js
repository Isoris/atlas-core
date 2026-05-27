// analysis/karyotype_polarizer/compute.js
//
// Polarization decision tree (per candidate):
//
//   if params.polarity_source == "force_unchanged"        → polarity = unchanged
//   elif "reference_match"                                → flip iff ref_dosage == "2"
//   elif "outgroup_vote" with sample(s) in outgroup_sample_ids
//                                                         → flip iff outgroup mean class > 1
//   elif "majority_allele"                                → flip iff mode(class) == "2"
//   else                                                  → polarity = unknown (call left as-is)
//
// "flip" swaps 0 ↔ 2; class "1" (heterozygote) is symmetric and never moves.
// NA propagates as NA; original_karyotype is preserved for audit.

const DEFAULTS = {
  candidate_id:        null,
  polarity_source:     "reference_match",
  outgroup_sample_ids: [],
  method_tag:          "polarize_v0",
};

function flip(klass) {
  if (klass === "0") return "2";
  if (klass === "2") return "0";
  return klass;           // "1" and "NA" unchanged
}

function modeClass(rows) {
  const counts = { "0": 0, "1": 0, "2": 0 };
  for (const r of rows) if (counts[r.karyotype] !== undefined) counts[r.karyotype] += 1;
  let best = "1", bestN = -1;
  for (const k of ["0", "1", "2"]) { if (counts[k] > bestN) { best = k; bestN = counts[k]; } }
  return best;
}

function meanClass(rows) {
  const nums = rows.map(r => +r.karyotype).filter(n => n === 0 || n === 1 || n === 2);
  if (!nums.length) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function decidePolarity(candidateId, p, callsForCand, refLayer) {
  if (p.polarity_source === "force_unchanged") {
    return { polarity: "unchanged", ref_dosage: null };
  }
  if (p.polarity_source === "reference_match") {
    const ref = (refLayer || []).find(r => r.candidate_id === candidateId);
    if (!ref) return { polarity: "unknown", ref_dosage: null };
    return { polarity: ref.ref_dosage === "2" ? "flipped" : "unchanged", ref_dosage: ref.ref_dosage };
  }
  if (p.polarity_source === "outgroup_vote") {
    const outRows = callsForCand.filter(r => p.outgroup_sample_ids.includes(r.sample_id));
    const m = meanClass(outRows);
    if (m === null) return { polarity: "unknown", ref_dosage: null };
    return { polarity: m > 1 ? "flipped" : "unchanged", ref_dosage: null };
  }
  if (p.polarity_source === "majority_allele") {
    const mc = modeClass(callsForCand);
    return { polarity: mc === "2" ? "flipped" : "unchanged", ref_dosage: null };
  }
  return { polarity: "unknown", ref_dosage: null };
}

export function compute(inputs, params = {}) {
  const p = { ...DEFAULTS, ...params };
  const calls = (inputs.unpolarized_karyotype_calls || [])
    .filter(c => !p.candidate_id || c.candidate_id === p.candidate_id);
  const refLayer = inputs.reference_genome_layer || [];
  const byCand = {};
  for (const c of calls) (byCand[c.candidate_id] = byCand[c.candidate_id] || []).push(c);

  const out = [];
  const summary = {};
  for (const cid of Object.keys(byCand)) {
    const rows = byCand[cid];
    const { polarity, ref_dosage } = decidePolarity(cid, p, rows, refLayer);
    let nFlipped = 0, nUnchanged = 0, nNa = 0;
    for (const r of rows) {
      const newClass = polarity === "flipped" ? flip(r.karyotype) : r.karyotype;
      const perRowPolarity = (polarity === "flipped" && newClass !== r.karyotype) ? "flipped" :
                             (polarity === "unknown" || r.karyotype === "NA")     ? (r.karyotype === "NA" ? "unknown" : "unknown") :
                             "unchanged";
      if (r.karyotype === "NA")        nNa += 1;
      else if (perRowPolarity === "flipped") nFlipped += 1;
      else                                    nUnchanged += 1;
      out.push({
        sample_id:          r.sample_id,
        candidate_id:       r.candidate_id,
        karyotype:          newClass,
        original_karyotype: r.karyotype,
        polarity:           r.karyotype === "NA" ? "unknown" : (polarity === "flipped" ? perRowPolarity : polarity),
        confidence:         r.confidence,
        method:             p.method_tag,
      });
    }
    summary[cid] = {
      candidate_id:      cid,
      polarity,
      polarity_source:   p.polarity_source,
      ref_dosage:        ref_dosage,
      n_flipped_calls:   nFlipped,
      n_unchanged_calls: nUnchanged,
      n_na_calls:        nNa,
    };
  }
  return { polarized_karyotype_calls: out, polarity_summary: summary };
}
