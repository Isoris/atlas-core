// analysis/inversion_pair_incompatibility/compute.js
//
// LG01 × LG28 pair-relation analysis (manuscript stress-test target).
//
// Given the candidate_registry (or inversion_candidates) + karyotype_calls
// for TWO candidates on different chromosomes, score whether the observed
// joint karyotype counts deviate from expected under independent
// transmission.  Per ADAPTER_CONTRACT.md §2: pure JSON-in / JSON-out, no
// registry imports, no DOM, no fetch.

export function compute(inputs, params) {
  const p = Object.assign({
    candidate_a: "inv_LG01_INV_001",
    candidate_b: "inv_LG28_INV_001",
    min_n_per_cell: 1,
  }, params || {});

  const candidates = inputs.inversion_candidates || inputs.candidate_registry || [];
  const karyo = inputs.karyotype_calls || [];

  const cands_by_id = Object.fromEntries(candidates.map(c => [c.candidate_id, c]));
  const ca = cands_by_id[p.candidate_a];
  const cb = cands_by_id[p.candidate_b];
  if (!ca || !cb) {
    return {
      distortion_summary: [],
      pair_meta: {
        candidate_a: p.candidate_a, candidate_b: p.candidate_b,
        status: "missing_candidate",
        reason: `candidate not found in inversion_candidates: ${ca ? p.candidate_b : p.candidate_a}`,
      },
    };
  }

  // Build per-sample karyotype lookups for each candidate
  const ka = Object.fromEntries(karyo.filter(r => r.candidate_id === p.candidate_a)
                                       .map(r => [r.sample_id, String(r.karyotype)]));
  const kb = Object.fromEntries(karyo.filter(r => r.candidate_id === p.candidate_b)
                                       .map(r => [r.sample_id, String(r.karyotype)]));

  // Sample intersection
  const samples = Object.keys(ka).filter(s => s in kb).sort();
  if (!samples.length) {
    return {
      distortion_summary: [],
      pair_meta: { candidate_a: p.candidate_a, candidate_b: p.candidate_b,
                   status: "no_overlap", n_samples: 0 },
    };
  }

  // 3 x 3 joint table
  const counts = {};
  for (const s of samples) {
    const k = `${ka[s]}|${kb[s]}`;
    counts[k] = (counts[k] || 0) + 1;
  }
  // marginals
  const marg_a = { "0": 0, "1": 0, "2": 0 };
  const marg_b = { "0": 0, "1": 0, "2": 0 };
  for (const s of samples) {
    marg_a[ka[s]] = (marg_a[ka[s]] || 0) + 1;
    marg_b[kb[s]] = (marg_b[kb[s]] || 0) + 1;
  }
  const N = samples.length;

  // Build the distortion_summary rows
  const out = [];
  for (const a of ["0", "1", "2"]) {
    for (const b of ["0", "1", "2"]) {
      const observed = counts[`${a}|${b}`] || 0;
      const expected = (marg_a[a] * marg_b[b]) / N;
      // chi-square contribution (only if expected > 0)
      const chi_sq = expected > 0 ? Math.pow(observed - expected, 2) / expected : 0;
      out.push({
        candidate_a: p.candidate_a,
        candidate_b: p.candidate_b,
        karyo_a: a,
        karyo_b: b,
        observed,
        expected: Math.round(expected * 100) / 100,
        chi_sq: Math.round(chi_sq * 1000) / 1000,
        cell_ok: observed >= p.min_n_per_cell,
      });
    }
  }
  const total_chi_sq = out.reduce((s, r) => s + r.chi_sq, 0);
  const df = 4; // (3-1) * (3-1)

  return {
    distortion_summary: out,
    pair_meta: {
      candidate_a: p.candidate_a, candidate_b: p.candidate_b,
      n_samples: N,
      total_chi_sq: Math.round(total_chi_sq * 1000) / 1000,
      df,
      status: "ok",
      cells_below_min: out.filter(r => !r.cell_ok).length,
    },
  };
}
