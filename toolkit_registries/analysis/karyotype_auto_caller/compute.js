// analysis/karyotype_auto_caller/compute.js
//
// Pure JSON-in / JSON-out. Calls per-(sample, candidate) karyotype
// 0/1/2 from dosage + chain_evidence + window_band_calls.
//
// Decision logic (intentionally simple v0; tunable via params):
//   class = bucket(dosage, params.dosage_breaks)
//   confidence:
//     high   if chain_score ≥ 0.80 AND band_fraction ≥ 0.80
//     medium if chain_score ≥ 0.50 AND band_fraction ≥ 0.60
//     low    otherwise
//   drop (emit NA) if confidence < params.confidence_floor
//
// A real production caller would do model-based clustering on the
// dosage distribution per candidate (k-means or GMM in 3-class mode)
// rather than fixed dosage_breaks; this v0 ships the contract + the
// thresholding strategy so downstream code can be wired today.

const DEFAULTS = {
  candidate_id:      null,
  min_chain_score:   0.50,
  min_band_fraction: 0.60,
  dosage_breaks:     [0.5, 1.5],
  confidence_floor:  "low",
  method_tag:        "auto_v0",
};
const CONF_ORDER = { "low": 0, "medium": 1, "high": 2 };

function bucket(dosage, breaks) {
  if (dosage === null || dosage === undefined || Number.isNaN(dosage)) return "NA";
  for (let i = 0; i < breaks.length; i++) {
    if (dosage < breaks[i]) return String(i);
  }
  return String(breaks.length);   // last bucket
}

function pickConfidence(chain, band, p) {
  if (chain >= 0.80 && band >= 0.80)                                   return "high";
  if (chain >= p.min_chain_score && band >= p.min_band_fraction)       return "medium";
  return "low";
}

export function compute(inputs, params = {}) {
  const p = { ...DEFAULTS, ...params };
  const candidates = (inputs.candidate_registry || [])
    .filter(c => !p.candidate_id || c.candidate_id === p.candidate_id);
  const idxBy = (arr, ka, kb) => {
    const m = {};
    for (const r of arr) m[`${r[ka]}|${r[kb]}`] = r;
    return m;
  };
  const chainBy  = idxBy(inputs.chain_evidence    || [], "sample_id", "candidate_id");
  const dosageBy = idxBy(inputs.dosage_summary    || [], "sample_id", "candidate_id");
  const bandBy   = idxBy(inputs.window_band_calls || [], "sample_id", "candidate_id");

  const calls = [];
  const summary = {};
  for (const c of candidates) {
    summary[c.candidate_id] = { n_total: 0, n_class_0: 0, n_class_1: 0, n_class_2: 0, n_na: 0, mean_chain_score: 0 };
    const sampleIds = new Set();
    for (const k of Object.keys(dosageBy)) {
      const [s, cid] = k.split("|");
      if (cid === c.candidate_id) sampleIds.add(s);
    }
    let sumChain = 0;
    for (const sid of sampleIds) {
      const key = `${sid}|${c.candidate_id}`;
      const dos = dosageBy[key] ? dosageBy[key].dosage : null;
      const chain = chainBy[key] ? chainBy[key].chain_score : 0;
      const band  = bandBy[key]  ? bandBy[key].band_fraction : 0;
      sumChain += chain;
      const conf = pickConfidence(chain, band, p);
      let klass = bucket(dos, p.dosage_breaks);
      let outConf = conf;
      let note;
      if (CONF_ORDER[conf] < CONF_ORDER[p.confidence_floor]) {
        klass = "NA";
        outConf = "low";
        note = `dropped: chain_score < min_chain_score (${p.min_chain_score}) AND band_fraction < min_band_fraction (${p.min_band_fraction})`;
      }
      const row = { sample_id: sid, candidate_id: c.candidate_id, karyotype: klass, dosage: dos,
                    chain_score: chain, band_fraction: band, confidence: outConf, method: p.method_tag };
      if (note) row.note = note;
      calls.push(row);
      summary[c.candidate_id].n_total += 1;
      if (klass === "0") summary[c.candidate_id].n_class_0 += 1;
      else if (klass === "1") summary[c.candidate_id].n_class_1 += 1;
      else if (klass === "2") summary[c.candidate_id].n_class_2 += 1;
      else summary[c.candidate_id].n_na += 1;
    }
    summary[c.candidate_id].mean_chain_score = sampleIds.size
      ? +(sumChain / sampleIds.size).toFixed(3) : 0;
  }
  return { unpolarized_karyotype_calls: calls, caller_summary: summary };
}
