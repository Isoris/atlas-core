// analysis/iv_candidate_promoter/compute.js
//
// Pure JSON-in / JSON-out promoter that turns window-band signals + L3
// contingency hits + dosage summaries into a candidate-interval registry
// with chain evidence.
//
// Per ADAPTER_CONTRACT.md §2 — this file:
//   - imports NOTHING (no registry, no DOM, no fetch)
//   - is deterministic given a seeded params.rng_seed (none here; the
//     promoter has no stochastic step)
//   - returns { candidate_registry: [...], chain_evidence: [...] }

export function compute(inputs, params) {
  const p = Object.assign({ min_band_score: 0.5, merge_windows_bp: 50000 }, params || {});
  const bands   = inputs.window_band_calls   || [];
  const l3      = inputs.l3_contingency      || [];
  const dosage  = inputs.dosage_summary      || [];

  // 1) keep bands at or above the threshold
  const kept = bands.filter(b => Number(b.band_score) >= p.min_band_score)
                    .sort((a, b) => a.chrom.localeCompare(b.chrom)
                                  || Number(a.start) - Number(b.start));

  // 2) merge contiguous bands per chromosome
  const merged = [];
  for (const b of kept) {
    const last = merged[merged.length - 1];
    if (last && last.chrom === b.chrom
        && Number(b.start) - Number(last.end) <= p.merge_windows_bp) {
      last.end = Math.max(Number(last.end), Number(b.end));
      last.band_count += 1;
      last.evidence_bands.push(b.window_id);
    } else {
      merged.push({
        chrom:         b.chrom,
        start:         Number(b.start),
        end:           Number(b.end),
        band_count:    1,
        evidence_bands:[b.window_id],
      });
    }
  }

  // 3) attach L3 + dosage hits per merged region; mint candidate_id
  const l3_by_chrom     = groupBy(l3,     r => r.chrom);
  const dosage_by_chrom = groupBy(dosage, r => r.chrom);
  const candidate_registry = [];
  const chain_evidence = [];

  merged.forEach((m, i) => {
    const candidate_id = `${m.chrom}_INV_${String(i + 1).padStart(3, "0")}`;
    const l3_hits     = (l3_by_chrom[m.chrom]     || []).filter(r => Number(r.pos)   >= m.start && Number(r.pos)   <= m.end);
    const dosage_hits = (dosage_by_chrom[m.chrom] || []).filter(r => Number(r.start) >= m.start && Number(r.end)   <= m.end);
    const confidence  = (l3_hits.length >= 2 && dosage_hits.length >= 1) ? "high" :
                        (l3_hits.length >= 1 || dosage_hits.length >= 1) ? "medium" : "low";
    candidate_registry.push({
      candidate_id,
      chrom:       m.chrom,
      start:       m.start,
      end:         m.end,
      band_count:  m.band_count,
      l3_hits:     l3_hits.length,
      dosage_hits: dosage_hits.length,
      confidence,
    });
    for (const w of m.evidence_bands) chain_evidence.push({ candidate_id, evidence_kind: "window_band", evidence_id: w });
    for (const r of l3_hits)     chain_evidence.push({ candidate_id, evidence_kind: "l3_contingency", evidence_id: r.site_id || `${r.chrom}:${r.pos}` });
    for (const r of dosage_hits) chain_evidence.push({ candidate_id, evidence_kind: "dosage_summary",   evidence_id: r.bin_id  || `${r.chrom}:${r.start}-${r.end}` });
  });

  return { candidate_registry, chain_evidence };
}

function groupBy(rows, keyfn) {
  const out = {};
  for (const r of rows) {
    const k = keyfn(r);
    (out[k] = out[k] || []).push(r);
  }
  return out;
}
