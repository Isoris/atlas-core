#!/usr/bin/env python3
# =============================================================================
# relatedness_compute.py
# =============================================================================
# Server-side ports of the four Mendelian / compatibility computes the
# Relatedness Atlas needs. Atlas-side falls back to in-browser compute when
# any of these is missing, but registering them here:
#   1. Eliminates the /compute/relatedness_* 404 probe noise.
#   2. Moves heavy work (cohort scan = candidates x triads) off the main
#      thread so the browser stays responsive on large cohorts.
#
# Reference impls (the in-browser source of truth — server port must match):
#   pages/hub/mendelian.js::runDyadTest        -> _compute_relatedness_mendelian_dyad_test
#   pages/hub/mendelian.js::runTriadTest       -> _compute_relatedness_mendelian_triad_test
#   pages/hub/inversions.js::scoreInversion    -> _compute_relatedness_cohort_mendelian_scan (async)
#   pages/hub/compatibility.js::runCompatibilitySearch -> _compute_relatedness_compatibility_search
#
# Stat primitives (logChoose, binomialPValueTwoSided, chiSquarePValue,
# expectedOffspringPrior) are ported verbatim from
# atlases/relatedness/shared/stats.js — same numerical recipe so server
# answers match the browser bit-for-bit (no scipy dependency added; the
# Wilson-Hilferty / Abramowitz primitives are tiny).
#
# Data sources (canonical TSVs under <project_root>/data/relatedness/):
#   inversion_karyotypes.tsv  — long form (sample_id, candidate, karyotype, quality)
#   inversion_catalogue.tsv   — per-candidate coordinates (candidate, chromosome, ...)
#   family_hub_roster.tsv     — sample_id -> family/hub/role
#   triads.tsv                — triad_id, parent_a, parent_b, offspring (+ optional valid/...)
#   per_chrom_qc.tsv          — triad-level trio_qc (valid, gw_mend_error, anc_dist)
#   sex.tsv (optional)        — sample_id, sex
#   network_edges.tsv (optional) — for exclude_kin
#
# When a required TSV is missing the handler raises a clean HTTPException-
# friendly RuntimeError that surfaces as the /compute endpoint's 500 with
# a message naming the file. Atlas-side's try/except falls back to the
# in-browser path so the UX degrades gracefully.
# =============================================================================

from __future__ import annotations

import math
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


SERVER_VERSION = "relatedness_compute.py v1.0.0"


# ---------------------------------------------------------------------------
# Statistical primitives — verbatim port of shared/stats.js
# ---------------------------------------------------------------------------

def log_choose(n: int, k: int) -> float:
    """log(C(n, k)). Mirrors logChoose() in shared/stats.js."""
    if k < 0 or k > n:
        return float("-inf")
    if k == 0 or k == n:
        return 0.0
    s = 0.0
    for i in range(1, k + 1):
        s += math.log(n - k + i) - math.log(i)
    return s


def binomial_p_two_sided(k: int, n: int, p: float) -> float:
    """Exact two-sided binomial p-value (sum of all PMF <= obs).

    Mirrors binomialPValueTwoSided() in shared/stats.js — including the
    +1e-12 tolerance on the comparison so float-equality ties get pooled
    on both sides exactly as the browser does.
    """
    if n == 0:
        return 1.0
    log_p = math.log(p)
    log_q = math.log(1.0 - p)

    def pmf(j: int) -> float:
        return math.exp(log_choose(n, j) + j * log_p + (n - j) * log_q)

    p_obs = pmf(k)
    total = 0.0
    for j in range(n + 1):
        pj = pmf(j)
        if pj <= p_obs + 1e-12:
            total += pj
    return min(1.0, total)


def chi_square_p(x: float, df: int) -> float:
    """Chi-square upper-tail p-value via Wilson-Hilferty + Abramowitz erf.

    Mirrors chiSquarePValue() in shared/stats.js — same constants, same
    cube-root transform, same erf approximation. Tested by the spec to
    match within 1e-15.
    """
    if x <= 0:
        return 1.0
    if df <= 0:
        return float("nan")
    t = (x / df) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))
    z = t / math.sqrt(2.0 / (9.0 * df))
    a1, a2, a3 = 0.254829592, -0.284496736, 1.421413741
    a4, a5, p_ = -1.453152027, 1.061405429, 0.3275911
    sign = -1.0 if z < 0 else 1.0
    xz = abs(z) / math.sqrt(2.0)
    t_ = 1.0 / (1.0 + p_ * xz)
    y = 1.0 - (((((a5 * t_ + a4) * t_) + a3) * t_ + a2) * t_ + a1) * t_ * math.exp(-xz * xz)
    phi = 0.5 * (1.0 + sign * y)
    return max(0.0, min(1.0, 1.0 - phi))


def expected_offspring_prior(p1: Optional[str], p2: Optional[str]) -> Optional[List[float]]:
    """Mirrors expectedOffspringPrior() in shared/stats.js. Returns
    [P(0/0), P(0/1), P(1/1)] or None if either parent karyotype is missing.
    """
    if not p1 or not p2 or p1 == "NA" or p2 == "NA":
        return None
    a = [int(x) for x in p1.split("/")]
    b = [int(x) for x in p2.split("/")]
    probs = [0.0, 0.0, 0.0]
    for a1 in a:
        for b1 in b:
            probs[a1 + b1] += 0.25
    return probs


def offspring_dist(p1: Optional[str], p2: Optional[str]) -> Optional[Dict[str, float]]:
    """Mirrors offspringDist() in pages/hub/compatibility.js."""
    if not p1 or not p2 or p1 == "NA" or p2 == "NA":
        return None
    probs = {"0/0": 0.0, "0/1": 0.0, "1/1": 0.0}
    a = [int(x) for x in p1.split("/")]
    b = [int(x) for x in p2.split("/")]
    for aa in a:
        for bb in b:
            s = aa + bb
            k = "0/0" if s == 0 else ("0/1" if s == 1 else "1/1")
            probs[k] += 0.25
    return probs


def norm_cdf(x: float) -> float:
    """Standard-normal CDF via Abramowitz erf. Mirrors normCdf() in
    pages/hub/mendelian.js (same constants → bit-identical output)."""
    a1, a2, a3 = 0.254829592, -0.284496736, 1.421413741
    a4, a5, p_ = -1.453152027, 1.061405429, 0.3275911
    sign = -1.0 if x < 0 else 1.0
    xz = abs(x) / math.sqrt(2.0)
    t_ = 1.0 / (1.0 + p_ * xz)
    y = 1.0 - (((((a5 * t_ + a4) * t_) + a3) * t_ + a2) * t_ + a1) * t_ * math.exp(-xz * xz)
    return 0.5 * (1.0 + sign * y)


def inv_norm_cdf(p: float) -> float:
    """Beasley-Springer-Moro inverse-normal CDF. Mirrors invNormCdf() in
    pages/hub/mendelian.js (same coefficients → bit-identical output)."""
    if p <= 0:
        return float("-inf")
    if p >= 1:
        return float("inf")
    a = [-3.969683028665376e+01,  2.209460984245205e+02,
         -2.759285104469687e+02,  1.383577518672690e+02,
         -3.066479806614716e+01,  2.506628277459239e+00]
    b = [-5.447609879822406e+01,  1.615858368580409e+02,
         -1.556989798598866e+02,  6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
          4.374664141464968e+00,  2.938163982698783e+00]
    d = [ 7.784695709041462e-03,  3.224671290700398e-01,
          2.445134137142996e+00,  3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return ((((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])
                / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1))
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q \
             / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -((((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])
             / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1))


def _stouffer_combined_p(per_result_ps: List[float]) -> float:
    """Two-sided Stouffer combination on a list of p-values. Mirrors the
    JS expression at mendelian.js combineCohortDyads / combineCohortTriads:
        z_combined = mean(invNormCdf(1 - p/2))      [only finite p's]
        combined_p = 2 * (1 - normCdf(|z_combined|))
    Returns NaN when no valid p-values."""
    finite = [p for p in per_result_ps if isinstance(p, (int, float)) and math.isfinite(p)]
    if not finite:
        return float("nan")
    z_sum = sum(inv_norm_cdf(1 - p / 2) for p in finite)
    z_combined = z_sum / math.sqrt(len(finite))
    return 2.0 * (1.0 - norm_cdf(abs(z_combined)))


# ---------------------------------------------------------------------------
# Canonical TSV loaders (mtime-cached)
# ---------------------------------------------------------------------------
# Each loader reads a single TSV under <project_root>/data/relatedness/.
# Results are cached in-memory keyed by (path, mtime) so repeat calls within
# a single server lifetime are O(1).

_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Tuple[float, Any]] = {}


def _cached_read(path: Path, parser) -> Any:
    with _CACHE_LOCK:
        key = str(path)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            raise RuntimeError(f"required TSV not found: {path}")
        cached = _CACHE.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]
    parsed = parser(path)
    with _CACHE_LOCK:
        _CACHE[key] = (mtime, parsed)
    return parsed


def _relatedness_dir(project_root: Path) -> Path:
    return project_root / "data" / "relatedness"


def _read_karyotype_matrix(project_root: Path) -> Dict[str, Any]:
    """Returns { 'karyotype_matrix': {sid: {inv: kt}}, 'karyotype_quality': {sid: {inv: q}},
                 'samples': [...], 'inversions': [{candidate, ...}] }.

    Reads inversion_karyotypes.tsv (long form) and optionally
    inversion_catalogue.tsv for the per-candidate coordinates.
    """
    path = _relatedness_dir(project_root) / "inversion_karyotypes.tsv"

    def _parse(p: Path) -> Dict[str, Any]:
        df = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
        # Accept either sample_id or sample as the id column; either
        # candidate / inversion_id / inv_id as the inv column.
        sid_col = next((c for c in ("sample_id", "sample") if c in df.columns), None)
        inv_col = next((c for c in ("candidate", "inversion_id", "inv_id") if c in df.columns), None)
        if sid_col is None or inv_col is None:
            raise RuntimeError(
                f"{p}: missing required columns (need sample_id + candidate)"
            )
        kt_col = "karyotype" if "karyotype" in df.columns else None
        q_col = "quality" if "quality" in df.columns else None
        matrix: Dict[str, Dict[str, str]] = {}
        quality: Dict[str, Dict[str, str]] = {}
        samples: set = set()
        inv_set: set = set()
        for _, r in df.iterrows():
            sid = r[sid_col]
            iid = r[inv_col]
            if not sid or not iid:
                continue
            samples.add(sid)
            inv_set.add(iid)
            matrix.setdefault(sid, {})[iid] = (r[kt_col] if kt_col else "NA") or "NA"
            quality.setdefault(sid, {})[iid] = (r[q_col] if q_col else "high") or "high"

        # Optional sidecar with coordinates.
        cat_path = _relatedness_dir(project_root) / "inversion_catalogue.tsv"
        if cat_path.exists():
            cdf = pd.read_csv(cat_path, sep="\t", dtype=str, keep_default_na=False)
            cand_col = next((c for c in ("candidate", "inversion_id") if c in cdf.columns), None)
            inversions = []
            for _, r in cdf.iterrows():
                cid = r.get(cand_col) if cand_col else None
                if not cid:
                    continue
                def _f(name, default=float("nan")):
                    v = r.get(name, "")
                    try:
                        return float(v) if v not in (None, "") else default
                    except ValueError:
                        return default
                inversions.append({
                    "candidate": cid,
                    "chromosome": r.get("chromosome") or r.get("chrom") or "?",
                    "start_mb": _f("start_mb"),
                    "end_mb": _f("end_mb"),
                    "length_mb": _f("length_mb"),
                    "frequency": _f("frequency", 0.0),
                    "status": r.get("status") or "pass",
                    "notes": r.get("notes") or "",
                })
        else:
            inversions = [{
                "candidate": c, "chromosome": "?",
                "start_mb": float("nan"), "end_mb": float("nan"),
                "length_mb": float("nan"), "frequency": float("nan"),
                "status": "unknown", "notes": "",
            } for c in sorted(inv_set)]

        return {
            "karyotype_matrix": matrix,
            "karyotype_quality": quality,
            "samples": sorted(samples),
            "inversions": inversions,
        }

    return _cached_read(path, _parse)


def _read_triads(project_root: Path) -> List[Dict[str, Any]]:
    """Returns [{id, parent_a, parent_b, offspring}, ...].

    Reads triads.tsv (canonical). Schema: triad_id, parent_a, parent_b,
    offspring. Optional valid/po_a/po_b/gw_mend_error/anc_dist columns
    feed trio_qc.
    """
    path = _relatedness_dir(project_root) / "triads.tsv"

    def _parse(p: Path) -> List[Dict[str, Any]]:
        df = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
        out = []
        for _, r in df.iterrows():
            tid = r.get("triad_id") or r.get("id")
            pa = r.get("parent_a") or r.get("parent1")
            pb = r.get("parent_b") or r.get("parent2")
            off = r.get("offspring")
            if not (tid and pa and pb and off):
                continue
            out.append({
                "id": tid,
                "parent_a": pa,
                "parent_b": pb,
                "offspring": off,
                # Optional trio_qc fields embedded in the same row:
                "_qc_inline": {
                    k: r[k] for k in ("valid", "po_a", "po_b", "gw_mend_error", "anc_dist")
                    if k in df.columns
                },
            })
        return out

    return _cached_read(path, _parse)


def _read_trio_qc(project_root: Path) -> Dict[str, Dict[str, Any]]:
    """Returns { triad_id: { valid, gw_mend_error, anc_dist, po_a, po_b } }.

    Pulled from per_chrom_qc.tsv when present; absent triads default to
    valid=True, gw_mend_error=0, anc_dist=0 to match the in-browser
    fallback at inversions.js classifyFamilyForInversion().
    """
    path = _relatedness_dir(project_root) / "per_chrom_qc.tsv"
    if not path.exists():
        return {}

    def _parse(p: Path) -> Dict[str, Dict[str, Any]]:
        df = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
        out: Dict[str, Dict[str, Any]] = {}
        for _, r in df.iterrows():
            tid = r.get("triad_id") or r.get("dyad_id") or r.get("id")
            if not tid or tid in out:
                continue
            out[tid] = {
                "valid": r.get("valid", "true").lower() != "false",
                "po_a": _maybe_float(r.get("po_a")),
                "po_b": _maybe_float(r.get("po_b")),
                "gw_mend_error": _maybe_float(r.get("gw_mend_error"), 0.0),
                "anc_dist": _maybe_float(r.get("anc_dist"), 0.0),
            }
        return out

    return _cached_read(path, _parse)


def _maybe_float(v: Any, default: float = float("nan")) -> float:
    try:
        if v in (None, ""):
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _read_individuals_and_sex(project_root: Path) -> Tuple[List[str], Dict[str, str]]:
    """family_hub_roster.tsv -> individuals list; sex.tsv -> sex map (optional)."""
    roster = _relatedness_dir(project_root) / "family_hub_roster.tsv"
    sex_path = _relatedness_dir(project_root) / "sex.tsv"

    def _parse_roster(p: Path) -> List[str]:
        df = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
        sid_col = next((c for c in ("sample_id", "individual_id", "id") if c in df.columns), None)
        if sid_col is None:
            raise RuntimeError(f"{p}: missing sample_id column")
        return [s for s in df[sid_col].tolist() if s]

    individuals: List[str] = []
    if roster.exists():
        individuals = _cached_read(roster, _parse_roster)

    sex_map: Dict[str, str] = {}
    if sex_path.exists():
        def _parse_sex(p: Path) -> Dict[str, str]:
            df = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
            sid_col = next((c for c in ("sample_id", "individual_id", "id") if c in df.columns), None)
            sex_col = next((c for c in ("sex", "Sex") if c in df.columns), None)
            if sid_col is None or sex_col is None:
                return {}
            return {r[sid_col]: r[sex_col] for _, r in df.iterrows() if r[sid_col]}
        sex_map = _cached_read(sex_path, _parse_sex)

    return individuals, sex_map


def _read_kin_edges(project_root: Path) -> List[Dict[str, str]]:
    """network_edges.tsv with columns (a, b, class). Optional."""
    path = _relatedness_dir(project_root) / "network_edges.tsv"
    if not path.exists():
        return []

    def _parse(p: Path) -> List[Dict[str, str]]:
        df = pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False)
        out = []
        for _, r in df.iterrows():
            if not (r.get("a") and r.get("b")):
                continue
            out.append({"a": r["a"], "b": r["b"], "class": r.get("class", "")})
        return out

    return _cached_read(path, _parse)


# ---------------------------------------------------------------------------
# Compute 1 — relatedness_mendelian_dyad_test (sync)
# ---------------------------------------------------------------------------

def _compute_relatedness_mendelian_dyad_test(
    args: Dict[str, Any], project_root: Path
) -> Dict[str, Any]:
    parent_id = args.get("parent_id")
    offspring_id = args.get("offspring_id")
    candidate_list = args.get("candidate_list") or []
    if not parent_id or not offspring_id:
        raise RuntimeError("dyad_test: parent_id and offspring_id required")

    kt = _read_karyotype_matrix(project_root)
    matrix = kt["karyotype_matrix"]
    pK = matrix.get(parent_id, {})
    oK = matrix.get(offspring_id, {})

    n_inf = n_zero = n_one = n_consistent = n_inconsistent = 0
    detail = []
    for c in candidate_list:
        # Atlas-side sends string candidate ids; tolerate dict form too.
        cid = c["candidate"] if isinstance(c, dict) else c
        p = pK.get(cid)
        o = oK.get(cid)
        if not p or p == "NA" or not o or o == "NA":
            continue
        if (p == "0/0" and o == "1/1") or (p == "1/1" and o == "0/0"):
            n_inconsistent += 1
            detail.append({"candidate": cid, "p_kt": p, "o_kt": o, "status": "fail"})
            continue
        n_consistent += 1
        if p == "0/1":
            if o == "0/0":
                n_zero += 1
                n_inf += 1
            elif o == "1/1":
                n_one += 1
                n_inf += 1
        detail.append({"candidate": cid, "p_kt": p, "o_kt": o, "status": "pass"})

    transmission_p = binomial_p_two_sided(n_zero, n_inf, 0.5) if n_inf > 0 else float("nan")
    n_total = n_consistent + n_inconsistent
    consistency_p = (
        binomial_p_two_sided(n_inconsistent, n_total, 0.02) if n_total > 0 else float("nan")
    )

    return {
        "mode": "dyad",
        "parent": parent_id,
        "offspring": offspring_id,
        "n_total": n_total,
        "n_consistent": n_consistent,
        "n_inconsistent": n_inconsistent,
        "n_informative": n_inf,
        "n_zero": n_zero,
        "n_one": n_one,
        "transmission_p": transmission_p,
        "consistency_p": consistency_p,
        "detail": detail,
        "produced_by": SERVER_VERSION,
        "produced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ---------------------------------------------------------------------------
# Compute 2 — relatedness_mendelian_triad_test (sync)
# ---------------------------------------------------------------------------

def _compute_relatedness_mendelian_triad_test(
    args: Dict[str, Any], project_root: Path
) -> Dict[str, Any]:
    p1_id = args.get("parent1_id")
    p2_id = args.get("parent2_id")
    o_id = args.get("offspring_id")
    candidate_list = args.get("candidate_list") or []
    if not (p1_id and p2_id and o_id):
        raise RuntimeError("triad_test: parent1_id, parent2_id, offspring_id required")

    kt = _read_karyotype_matrix(project_root)
    matrix = kt["karyotype_matrix"]
    p1K = matrix.get(p1_id, {})
    p2K = matrix.get(p2_id, {})
    oK = matrix.get(o_id, {})

    n_total = n_consistent = n_inconsistent = n_het_het = 0
    n_het_het_obs00 = n_het_het_obs01 = n_het_het_obs11 = 0
    detail = []
    for c in candidate_list:
        cid = c["candidate"] if isinstance(c, dict) else c
        p1 = p1K.get(cid)
        p2 = p2K.get(cid)
        o = oK.get(cid)
        if (not p1 or p1 == "NA" or not p2 or p2 == "NA" or not o or o == "NA"):
            continue
        expected = expected_offspring_prior(p1, p2)
        if expected is None:
            continue
        o_idx = 0 if o == "0/0" else (1 if o == "0/1" else 2)
        is_in_expected = expected[o_idx] > 0
        n_total += 1
        if is_in_expected:
            n_consistent += 1
        else:
            n_inconsistent += 1
        if p1 == "0/1" and p2 == "0/1":
            n_het_het += 1
            if o == "0/0":
                n_het_het_obs00 += 1
            elif o == "0/1":
                n_het_het_obs01 += 1
            else:
                n_het_het_obs11 += 1
        detail.append({
            "candidate": cid, "p1_kt": p1, "p2_kt": p2, "o_kt": o,
            "expected": expected,
            "status": "pass" if is_in_expected else "fail",
        })

    consistency_p = (
        binomial_p_two_sided(n_inconsistent, n_total, 0.02) if n_total > 0 else float("nan")
    )
    chi2 = chi2_p = float("nan")
    chi2_df = 2
    if n_het_het >= 5:
        exp00 = n_het_het * 0.25
        exp01 = n_het_het * 0.50
        exp11 = n_het_het * 0.25
        x = (
            (n_het_het_obs00 - exp00) ** 2 / exp00
            + (n_het_het_obs01 - exp01) ** 2 / exp01
            + (n_het_het_obs11 - exp11) ** 2 / exp11
        )
        chi2 = x
        chi2_p = chi_square_p(x, chi2_df)

    return {
        "mode": "triad",
        "parent1": p1_id, "parent2": p2_id, "offspring": o_id,
        "n_total": n_total,
        "n_consistent": n_consistent,
        "n_inconsistent": n_inconsistent,
        "consistency_p": consistency_p,
        "n_het_het": n_het_het,
        "n_het_het_obs00": n_het_het_obs00,
        "n_het_het_obs01": n_het_het_obs01,
        "n_het_het_obs11": n_het_het_obs11,
        "chi2": chi2, "chi2_p": chi2_p, "chi2_df": chi2_df,
        "detail": detail,
        "produced_by": SERVER_VERSION,
        "produced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ---------------------------------------------------------------------------
# Compute 2b — relatedness_mendelian_cohort_dyads (sync)
# Compute 2c — relatedness_mendelian_cohort_triads (sync)
# ---------------------------------------------------------------------------
# Mirror combineCohortDyads / combineCohortTriads in pages/hub/mendelian.js.
# Browser passes the explicit hub+partners (or parents+offspring) so the server
# stays decoupled from family_hub_roster — runDyadTest/runTriadTest are run per
# dyad/triad and their consistency_p's are Stouffer-combined.

def _compute_relatedness_mendelian_cohort_dyads(
    args: Dict[str, Any], project_root: Path
) -> Dict[str, Any]:
    hub_id = args.get("hub_id")
    partner_ids = args.get("partner_ids") or []
    candidate_list = args.get("candidate_list") or []
    if not hub_id or not partner_ids:
        raise RuntimeError("cohort_dyads: hub_id and partner_ids (non-empty) required")

    results = []
    for partner in partner_ids:
        results.append(_compute_relatedness_mendelian_dyad_test(
            {"parent_id": hub_id, "offspring_id": partner,
             "candidate_list": candidate_list},
            project_root,
        ))

    combined_p = _stouffer_combined_p([r["consistency_p"] for r in results])

    return {
        "mode": "all_dyads",
        "hub": hub_id,
        "n_dyads": len(results),
        "results": results,
        "combined_p": combined_p,
        "summary": [{
            "pair": f"{r['parent']} × {r['offspring']}",
            "consistency_p": r["consistency_p"],
            "n_total": r["n_total"],
            "n_inconsistent": r["n_inconsistent"],
        } for r in results],
        "produced_by": SERVER_VERSION,
        "produced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _compute_relatedness_mendelian_cohort_triads(
    args: Dict[str, Any], project_root: Path
) -> Dict[str, Any]:
    p1_id = args.get("parent1_id")
    p2_id = args.get("parent2_id")
    offspring_ids = args.get("offspring_ids") or []
    candidate_list = args.get("candidate_list") or []
    if not (p1_id and p2_id and offspring_ids):
        raise RuntimeError(
            "cohort_triads: parent1_id, parent2_id, offspring_ids (non-empty) required"
        )

    results = []
    for off in offspring_ids:
        results.append(_compute_relatedness_mendelian_triad_test(
            {"parent1_id": p1_id, "parent2_id": p2_id, "offspring_id": off,
             "candidate_list": candidate_list},
            project_root,
        ))

    combined_p = _stouffer_combined_p([r["consistency_p"] for r in results])

    return {
        "mode": "all_triads",
        "parent1": p1_id,
        "parent2": p2_id,
        "n_triads": len(results),
        "results": results,
        "combined_p": combined_p,
        "summary": [{
            "pair": f"{r['parent1']} × {r['parent2']} → {r['offspring']}",
            "consistency_p": r["consistency_p"],
            "chi2_p": r["chi2_p"],
            "n_total": r["n_total"],
            "n_inconsistent": r["n_inconsistent"],
        } for r in results],
        "produced_by": SERVER_VERSION,
        "produced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ---------------------------------------------------------------------------
# Compute 3 — relatedness_compatibility_search (sync)
# ---------------------------------------------------------------------------

_COMPAT_VERDICT_ORDER = {"ideal": 0, "good": 1, "possible": 2, "unknown": 3, "reject": 4}


def _evaluate_partnership(
    focal_id: str, partner_id: str, inv_set: List[Dict[str, Any]],
    target_kt: str, matrix: Dict[str, Dict[str, str]]
) -> Dict[str, Any]:
    focal_k = matrix.get(focal_id, {})
    partner_k = matrix.get(partner_id, {})
    per_inv = []
    n_guaranteed = n_possible = n_impossible = n_unknown = 0
    for inv in inv_set:
        cid = inv["candidate"]
        fk = focal_k.get(cid)
        pk = partner_k.get(cid)
        if not fk or not pk or fk == "NA" or pk == "NA":
            per_inv.append({
                "inv": cid, "focal_kt": fk or "NA", "partner_kt": pk or "NA",
                "prob_target": None, "status": "unknown",
            })
            n_unknown += 1
            continue
        dist = offspring_dist(fk, pk) or {}
        p = dist.get(target_kt, 0.0)
        if p >= 0.999:
            status = "guaranteed"
            n_guaranteed += 1
        elif p > 0:
            status = "possible"
            n_possible += 1
        else:
            status = "impossible"
            n_impossible += 1
        per_inv.append({
            "inv": cid, "focal_kt": fk, "partner_kt": pk,
            "prob_target": p, "status": status,
        })

    if n_impossible > 0:
        verdict = "reject"
    elif n_guaranteed == (len(inv_set) - n_unknown) and n_guaranteed > 0:
        verdict = "ideal"
    elif n_guaranteed > 0:
        verdict = "good"
    elif n_possible > 0:
        verdict = "possible"
    else:
        verdict = "unknown"

    return {
        "partner_id": partner_id,
        "n_guaranteed": n_guaranteed,
        "n_possible": n_possible,
        "n_impossible": n_impossible,
        "n_unknown": n_unknown,
        "verdict": verdict,
        "perInv": per_inv,
    }


def _compute_relatedness_compatibility_search(
    args: Dict[str, Any], project_root: Path
) -> Dict[str, Any]:
    focal_id = args.get("focal_id")
    target_kt = args.get("target_karyotype")
    scope = args.get("scope", "all")
    inv_single = args.get("inv_single")
    chrom = args.get("chrom")
    sex_aware = bool(args.get("sex_aware", False))
    exclude_kin = bool(args.get("exclude_kin", False))
    exclude_ambig = bool(args.get("exclude_ambig", False))
    if not focal_id or target_kt not in ("0/0", "0/1", "1/1"):
        raise RuntimeError("compatibility_search: focal_id and target_karyotype (0/0|0/1|1/1) required")

    kt = _read_karyotype_matrix(project_root)
    matrix = kt["karyotype_matrix"]
    all_inversions = kt["inversions"]
    if scope == "single":
        inv_set = [i for i in all_inversions if i["candidate"] == inv_single]
    elif scope == "chrom":
        inv_set = [i for i in all_inversions if i["chromosome"] == chrom]
    else:
        inv_set = list(all_inversions)

    individuals, sex_map = _read_individuals_and_sex(project_root)
    if not individuals:
        # Fall back to whatever sample ids the karyotype matrix knows about.
        individuals = list(matrix.keys())

    candidates = [p for p in individuals if p != focal_id]
    sex_data_available = True
    sex_filter_applied = False
    if sex_aware:
        focal_sex = sex_map.get(focal_id)
        if not focal_sex or focal_sex in ("?", "unknown"):
            sex_data_available = False
        else:
            candidates = [p for p in candidates
                          if sex_map.get(p) and sex_map.get(p) != "?" and sex_map.get(p) != focal_sex]
            sex_filter_applied = True

    if exclude_kin:
        edges = _read_kin_edges(project_root)
        kin = set()
        for e in edges:
            if e["class"] in ("strong_po", "possible_po"):
                if e["a"] == focal_id:
                    kin.add(e["b"])
                if e["b"] == focal_id:
                    kin.add(e["a"])
        candidates = [p for p in candidates if p not in kin]

    results = [
        _evaluate_partnership(focal_id, p, inv_set, target_kt, matrix)
        for p in candidates
    ]

    # Literal "Exclude ambiguous karyotypes" — drop partners with any NA
    # in the tested inversion scope. Mirrors compatibility.js. Default-ON
    # in the browser; uncheck for sparse-data cohorts.
    n_before_ambig_filter = len(results)
    if exclude_ambig:
        results = [r for r in results if r["n_unknown"] == 0]
    n_excluded_ambig = n_before_ambig_filter - len(results) if exclude_ambig else 0

    results.sort(key=lambda r: (_COMPAT_VERDICT_ORDER.get(r["verdict"], 99), -r["n_guaranteed"]))

    return {
        "focal": focal_id,
        "target": target_kt,
        "invSet": inv_set,
        "sex_data_available": sex_data_available,
        "sex_filter_applied": sex_filter_applied,
        "n_excluded_ambig": n_excluded_ambig,
        "results": results,
        "produced_by": SERVER_VERSION,
        "produced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ---------------------------------------------------------------------------
# Compute 4 — relatedness_cohort_mendelian_scan (async via JobManager)
# ---------------------------------------------------------------------------
# Mirrors pages/hub/inversions.js scoreInversion called for every candidate.
# Heavy: O(candidates x triads). Runs in a worker thread; handler returns
# {job_id, status:'pending'} immediately and atlas_server's /api/jobs/<id>
# endpoint surfaces progress + final result.

_MENDEL_RULES: Dict[str, List[str]] = {}


def _init_mendel_rules() -> None:
    if _MENDEL_RULES:
        return
    pairs = [
        ("0/0", "0/0", ["0/0"]),
        ("1/1", "1/1", ["1/1"]),
        ("0/0", "1/1", ["0/1"]),
        ("0/0", "0/1", ["0/0", "0/1"]),
        ("1/1", "0/1", ["0/1", "1/1"]),
        ("0/1", "0/1", ["0/0", "0/1", "1/1"]),
    ]
    for p1, p2, allowed in pairs:
        k = "|".join(sorted([p1, p2]))
        _MENDEL_RULES[k] = allowed


def _expected_offspring_set(p1: str, p2: str) -> Optional[List[str]]:
    if not p1 or not p2 or p1 == "NA" or p2 == "NA":
        return None
    return _MENDEL_RULES.get("|".join(sorted([p1, p2])))


def _is_diagnostic_parents(p1: str, p2: str) -> bool:
    k = "|".join(sorted([p1, p2]))
    return k in ("0/0|0/0", "1/1|1/1", "0/0|1/1")


def _classify_family_for_inversion(
    triad: Dict[str, Any], inv_id: str,
    matrix: Dict[str, Dict[str, str]], quality: Dict[str, Dict[str, str]],
    trio_qc_map: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    p1 = (matrix.get(triad["parent_a"]) or {}).get(inv_id)
    p2 = (matrix.get(triad["parent_b"]) or {}).get(inv_id)
    o = (matrix.get(triad["offspring"]) or {}).get(inv_id)
    q1 = (quality.get(triad["parent_a"]) or {}).get(inv_id, "high")
    q2 = (quality.get(triad["parent_b"]) or {}).get(inv_id, "high")
    qo = (quality.get(triad["offspring"]) or {}).get(inv_id, "high")
    any_low = (q1 == "low" or q2 == "low" or qo == "low")

    qc = trio_qc_map.get(triad["id"])
    if qc is None:
        # Fall back to inline QC carried on the triad row, or default-valid.
        inline = triad.get("_qc_inline") or {}
        qc = {
            "valid": str(inline.get("valid", "true")).lower() != "false",
            "gw_mend_error": _maybe_float(inline.get("gw_mend_error"), 0.0),
            "anc_dist": _maybe_float(inline.get("anc_dist"), 0.0),
        }
    family_valid = qc.get("valid", True)

    if not p1 or not p2 or not o or p1 == "NA" or p2 == "NA" or o == "NA":
        return {
            "family_id": triad["id"],
            "parent_a": triad["parent_a"], "parent_b": triad["parent_b"],
            "offspring": triad["offspring"],
            "p1_kt": p1 or "NA", "p2_kt": p2 or "NA", "o_kt": o or "NA",
            "expected": None, "status": "not_informative",
            "diagnostic": False, "family_valid": family_valid, "qc": qc,
        }
    expected = _expected_offspring_set(p1, p2)
    diagnostic = _is_diagnostic_parents(p1, p2)
    compatible = expected is not None and o in expected
    if not compatible:
        status = "fail" if family_valid else "family_warn"
    elif any_low:
        status = "warn"
    else:
        status = "pass"
    return {
        "family_id": triad["id"],
        "parent_a": triad["parent_a"], "parent_b": triad["parent_b"],
        "offspring": triad["offspring"],
        "p1_kt": p1, "p2_kt": p2, "o_kt": o,
        "expected": expected, "status": status, "diagnostic": diagnostic,
        "anyLowConf": any_low,
        "family_valid": family_valid, "qc": qc,
    }


def _score_inversion(
    inv_id: str, triads: List[Dict[str, Any]],
    matrix: Dict[str, Dict[str, str]], quality: Dict[str, Dict[str, str]],
    trio_qc_map: Dict[str, Dict[str, Any]],
    alpha: float,
) -> Dict[str, Any]:
    _init_mendel_rules()
    families = [_classify_family_for_inversion(t, inv_id, matrix, quality, trio_qc_map)
                for t in triads]
    informative = [f for f in families if f["status"] != "not_informative"]
    valid_inf = [f for f in informative if f["family_valid"] is not False]
    suspect_inf = [f for f in informative if f["family_valid"] is False]
    diagnostic_families = [f for f in valid_inf if f["diagnostic"]]

    n_pass = sum(1 for f in valid_inf if f["status"] == "pass")
    n_warn = sum(1 for f in valid_inf if f["status"] == "warn")
    n_fail = sum(1 for f in valid_inf if f["status"] == "fail")
    n_inf = len(valid_inf)
    pass_frac = (n_pass / n_inf) if n_inf > 0 else 0.0
    n_suspect_fail = sum(1 for f in suspect_inf if f["status"] in ("fail", "family_warn"))

    n_t0 = n_t1 = n_het_parents_used = 0
    family_directions = []

    def _tally(parent_kt: str, partner_kt: str, off_kt: str) -> Optional[int]:
        if parent_kt != "0/1":
            return None
        if partner_kt == "0/0":
            if off_kt == "0/0":
                return 0
            if off_kt == "0/1":
                return 1
            return None
        if partner_kt == "1/1":
            if off_kt == "0/1":
                return 0
            if off_kt == "1/1":
                return 1
            return None
        if partner_kt == "0/1":
            if off_kt == "0/0":
                return 0
            if off_kt == "1/1":
                return 1
            return None
        return None

    for f in valid_inf:
        fam_t0 = fam_t1 = 0
        t_a = _tally(f["p1_kt"], f["p2_kt"], f["o_kt"])
        t_b = _tally(f["p2_kt"], f["p1_kt"], f["o_kt"])
        if t_a == 0:
            fam_t0 += 1
        elif t_a == 1:
            fam_t1 += 1
        if t_b == 0:
            fam_t0 += 1
        elif t_b == 1:
            fam_t1 += 1
        n_t0 += fam_t0
        n_t1 += fam_t1
        total = fam_t0 + fam_t1
        if total > 0:
            n_het_parents_used += total
            d = "over_1" if fam_t1 > fam_t0 else ("over_0" if fam_t0 > fam_t1 else "balanced")
            family_directions.append({"family_id": f["family_id"], "t0": fam_t0, "t1": fam_t1, "dir": d})
        else:
            family_directions.append({"family_id": f["family_id"], "t0": 0, "t1": 0, "dir": "na"})

    n_total_t = n_t0 + n_t1
    trans_p = float("nan")
    trans_skew_dir = "none"
    if n_total_t >= 4:
        k = min(n_t0, n_t1)
        trans_p = binomial_p_two_sided(k, n_total_t, 0.5)
        if n_t1 > n_t0:
            trans_skew_dir = "over_1"
        elif n_t0 > n_t1:
            trans_skew_dir = "over_0"
        else:
            trans_skew_dir = "balanced"
    concordant_families = sum(1 for d in family_directions if d["dir"] == trans_skew_dir)

    # Category ladder — mirrors inversions.js verbatim. `alpha` is the
    # significance threshold; JS uses hard 0.05 / 0.02 — we expose alpha
    # for the strong cutoff (0.05) so the cohort UI can sweep.
    if n_inf < 3:
        category = "NEEDS_CROSSES"
        verdict = "Insufficient informative families — design crosses to validate"
    elif pass_frac < 0.70:
        if n_suspect_fail > n_fail:
            category = "WARN_FAMILY"
            verdict = "Failures concentrated in suspect trios — review annotation"
        else:
            category = "LOCAL_CONFLICT"
            verdict = "Valid families show repeated Mendelian inconsistencies at this locus"
    elif n_fail >= 2:
        category = "LOCAL_CONFLICT"
        verdict = "Valid families show repeated Mendelian inconsistencies at this locus"
    elif (math.isfinite(trans_p) and trans_p < 0.02
          and n_total_t >= 8 and concordant_families >= 5):
        category = "DRIVE_CANDIDATE"
        verdict = (f"Transmission distortion repeated across {concordant_families} "
                   f"independent valid families (binomial p = {trans_p:.2e})")
    elif math.isfinite(trans_p) and trans_p < alpha and n_total_t >= 6:
        category = "TRANSMISSION_SKEW"
        pct = (max(n_t0, n_t1) / n_total_t * 100.0) if n_total_t > 0 else 0.0
        verdict = (f"Heterozygous parents transmit one allele at {pct:.0f}% "
                   f"(binomial p = {trans_p:.3f}); needs more families before drive call")
    elif n_warn > 0 and (n_pass + n_warn) == n_inf:
        category = "WARN_CALL"
        verdict = "Mendelian-compatible across all valid families, but some calls are low-confidence"
    else:
        category = "PASS"
        verdict = "Mendelian-compatible inversion candidate"

    if category == "DRIVE_CANDIDATE":
        tier = "drive"
    elif category == "TRANSMISSION_SKEW":
        tier = "skew"
    elif category == "LOCAL_CONFLICT":
        tier = "conflict"
    elif category == "WARN_FAMILY":
        tier = "warn_family"
    elif category == "NEEDS_CROSSES":
        tier = "needs_crosses"
    elif category == "WARN_CALL":
        tier = "moderate"
    elif n_inf >= 5 and pass_frac >= 0.90 and n_fail == 0:
        tier = "strong"
    elif n_inf >= 3 and pass_frac >= 0.70:
        tier = "moderate"
    else:
        tier = "weak"

    aura = 0.0
    if tier == "strong":
        aura = min(1.0, 0.5 + 0.5 * pass_frac + 0.05 * min(n_inf - 5, 5))
        aura -= 0.05 * n_warn
        aura = max(0.4, min(1.0, aura))
    elif tier == "drive":
        skew_mag = abs(n_t1 - n_t0) / n_total_t if n_total_t > 0 else 0.0
        aura = min(1.0, 0.5 + 0.5 * skew_mag)

    return {
        "inv_id": inv_id,
        "n_informative": n_inf,
        "n_diagnostic": len(diagnostic_families),
        "n_pass": n_pass, "n_warn": n_warn, "n_fail": n_fail,
        "n_suspect_inf": len(suspect_inf),
        "n_suspect_fail": n_suspect_fail,
        "pass_frac": pass_frac, "tier": tier,
        "category": category, "verdict": verdict,
        "families": families,
        "valid_families": valid_inf,
        "suspect_families": suspect_inf,
        "n_transmissions_0": n_t0,
        "n_transmissions_1": n_t1,
        "n_total_t": n_total_t,
        "trans_p": trans_p,
        "trans_skew_dir": trans_skew_dir,
        "family_directions": family_directions,
        "concordant_families": concordant_families,
        "aura_intensity": aura,
    }


def make_cohort_scan_handler(jobs_manager) -> Any:
    """Returns a `(args, project_root) -> {job_id, status}` handler that
    schedules the heavy scan in a worker thread. atlas_server passes its
    JobManager singleton (the `JOBS` global) in via this factory because
    the JobState dataclass lives in atlas_server, not here.
    """

    def _handler(args: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
        candidate_ids = args.get("candidate_ids")
        triad_ids = args.get("triad_ids")
        alpha = float(args.get("alpha", 0.05))
        include_suspect = bool(args.get("include_suspect_trios", True))

        kt = _read_karyotype_matrix(project_root)
        matrix = kt["karyotype_matrix"]
        quality = kt["karyotype_quality"]
        all_inversions = kt["inversions"]
        triads = _read_triads(project_root)
        trio_qc_map = _read_trio_qc(project_root)

        if candidate_ids:
            wanted = set(candidate_ids)
            all_inversions = [i for i in all_inversions if i["candidate"] in wanted]
        if triad_ids:
            wanted_t = set(triad_ids)
            triads = [t for t in triads if t["id"] in wanted_t]
        if not include_suspect:
            triads = [t for t in triads
                      if trio_qc_map.get(t["id"], {}).get("valid", True) is not False]

        st = jobs_manager.new(kind="relatedness_cohort_mendelian_scan", chrom="*")
        st.status = "running"
        st.message = f"scoring {len(all_inversions)} candidates x {len(triads)} triads"

        def _worker():
            try:
                scores = []
                total = max(1, len(all_inversions))
                for i, inv in enumerate(all_inversions):
                    s = _score_inversion(
                        inv["candidate"], triads, matrix, quality, trio_qc_map, alpha
                    )
                    scores.append(s)
                    # Progress: update every 8 candidates to keep overhead low.
                    if (i & 7) == 0:
                        st.progress = (i + 1) / total
                st.progress = 1.0
                st.result = {
                    "n_candidates": len(scores),
                    "scores": scores,
                    "alpha": alpha,
                    "include_suspect_trios": include_suspect,
                    "produced_by": SERVER_VERSION,
                    "produced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                st.status = "done"
                st.finished_at = time.time()
            except Exception as exc:  # noqa: BLE001
                st.status = "error"
                st.error = f"{type(exc).__name__}: {exc}"
                st.finished_at = time.time()

        threading.Thread(target=_worker, name=f"cohort-scan-{st.job_id}", daemon=True).start()
        return {"job_id": st.job_id, "status": "pending", "kind": st.kind}

    return _handler


# ---------------------------------------------------------------------------
# Public registry mounter
# ---------------------------------------------------------------------------

def register_handlers(compute_registry: Dict[str, Any], jobs_manager: Any) -> None:
    """Adds the six relatedness handlers to atlas_server's COMPUTE_REGISTRY.

    Called from atlas_server.py once at module load. `jobs_manager` is the
    JOBS singleton (JobManager instance) so the async cohort scan can park
    progress + final result there for /api/jobs/<id> polling.
    """
    compute_registry["relatedness_mendelian_dyad_test"]    = _compute_relatedness_mendelian_dyad_test
    compute_registry["relatedness_mendelian_triad_test"]   = _compute_relatedness_mendelian_triad_test
    compute_registry["relatedness_mendelian_cohort_dyads"] = _compute_relatedness_mendelian_cohort_dyads
    compute_registry["relatedness_mendelian_cohort_triads"]= _compute_relatedness_mendelian_cohort_triads
    compute_registry["relatedness_compatibility_search"]   = _compute_relatedness_compatibility_search
    compute_registry["relatedness_cohort_mendelian_scan"]  = make_cohort_scan_handler(jobs_manager)
