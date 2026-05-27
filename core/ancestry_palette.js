// atlas-core/core/ancestry_palette.js
// =============================================================================
// Canonical ancestry palette for the atlas family.
//
// Twenty colors at saturation 500 from the Tailwind palette — chosen so cluster
// bars across atlases (relatedness karyotype stripes, population NGSadmix Q
// bars, heterozygosity ancestry-stratified boxplots, BDMI / popstats group
// pills) all share one visual identity instead of each module rolling its own
// random colors.
//
// Positions 1..8 are the original K=8 palette pinned at 2026-05-23 (matches
// the inversion atlas defaults — see relatedness-atlas/shared/demo_data.js
// before this module landed). Positions 9..20 extend the same family to
// cover NGSadmix sweeps up to K=20 without color repetition.
//
// Usage:
//   import { ANCESTRY_PALETTE, ancestryColor } from '../../../core/ancestry_palette.js';
//   const fill = ancestryColor(k);                       // mod-wraps for k >= 20
//   const fills = ANCESTRY_PALETTE.slice(0, K);          // first K colors
//
// CSS-side consumers can either import this module and inject inline styles,
// or use the matching CSS custom-property block in atlas-core/css/tokens.css
// (--anc-1..--anc-20, kept in sync with this file).
// =============================================================================

export const ANCESTRY_PALETTE = Object.freeze([
  '#3b82f6', //  1  blue-500     (atlas K=8 default)
  '#f97316', //  2  orange-500   (atlas K=8 default)
  '#10b981', //  3  emerald-500  (atlas K=8 default)
  '#8b5cf6', //  4  violet-500   (atlas K=8 default)
  '#ec4899', //  5  pink-500     (atlas K=8 default)
  '#f59e0b', //  6  amber-500    (atlas K=8 default)
  '#06b6d4', //  7  cyan-500     (atlas K=8 default)
  '#94a3b8', //  8  slate-500    (atlas K=8 default)
  '#f43f5e', //  9  rose-500
  '#14b8a6', // 10  teal-500
  '#84cc16', // 11  lime-500
  '#6366f1', // 12  indigo-500
  '#d946ef', // 13  fuchsia-500
  '#eab308', // 14  yellow-500
  '#0ea5e9', // 15  sky-500
  '#a855f7', // 16  purple-500
  '#22c55e', // 17  green-500
  '#ef4444', // 18  red-500
  '#64748b', // 19  slate-600-ish (darker neutral)
  '#78716c', // 20  stone-500
]);

/**
 * Return the canonical color for cluster index k (zero-based).
 * Wraps modulo 20 so callers can pass any non-negative integer.
 */
export function ancestryColor(k) {
  if (!Number.isFinite(k) || k < 0) return ANCESTRY_PALETTE[ANCESTRY_PALETTE.length - 1];
  return ANCESTRY_PALETTE[k % ANCESTRY_PALETTE.length];
}

/**
 * Return the first K colors (typically used to seed an NGSadmix legend).
 * Slices into a fresh array (caller can mutate without affecting the frozen master).
 */
export function ancestrySlice(K) {
  if (!Number.isFinite(K) || K <= 0) return [];
  const n = Math.min(K, ANCESTRY_PALETTE.length);
  return ANCESTRY_PALETTE.slice(0, n);
}
