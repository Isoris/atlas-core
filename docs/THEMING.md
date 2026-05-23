# THEMING — atlas-core token system + per-atlas consumption

**Audience**: anyone writing CSS for an atlas page or the shell.

**Source of truth**: [`atlas-core/css/tokens.css`](../css/tokens.css).

---

## 1. Three themes

`<html data-theme>` selects one of three palettes. Cycled by the
`#themeToggleBtn` in the shell header
([`core/shell_chrome.js::_wireThemeToggle`](../core/shell_chrome.js)), persisted in
`localStorage` under `atlas.theme`.

| theme        | when active                                | feel                                             |
|--------------|--------------------------------------------|--------------------------------------------------|
| `dark`       | default (no `data-theme` attr or = `dark`) | deep blue-grey panels, amber accent              |
| `light`      | `<html data-theme="light">`                | clean off-white, darker amber for legibility     |
| `academic`   | `<html data-theme="academic">`             | warm ivory paper, desaturated slate/ochre/sage   |

The cycle order is dark → light → academic → dark. The button label
previews the next theme (e.g. shows "☀ light" when current is dark).

## 2. Token list

`:root` in `tokens.css` defines every theme-aware variable:

| token                | semantics                                          |
|----------------------|----------------------------------------------------|
| `--bg`               | deepest page background                            |
| `--panel`            | card / panel surface                               |
| `--panel-2`          | secondary surface (subtle hover, nested cards)     |
| `--panel-3`          | tertiary tray (rare; focus state)                  |
| `--ink`              | primary text                                       |
| `--ink-dim`          | secondary text (muted)                             |
| `--ink-dimmer`       | tertiary text (placeholders, disabled)             |
| `--rule`             | borders, separators                                |
| `--accent`           | primary accent (warm amber → ochre across themes)  |
| `--accent-2`         | secondary accent (blue → slate across themes)      |
| `--good`             | success state                                      |
| `--bad`              | error state                                        |
| `--neutral`          | quiet status                                       |
| `--band-lo / mid / hi` | three-bucket categorical (e.g. karyotype 0/1/2)  |
| `--l1-color / l2-color` | overlay PDF envelope colours                    |
| `--status-stable / marginal / decays / edge / dedup` | per-stability-band tints     |
| `--mono`             | monospace font stack                               |
| `--serif`            | serif font stack (academic theme uses it for prose) |

Each `html[data-theme="..."]` block re-defines these. Tokens that aren't
re-defined in a theme block fall through to the `:root` (dark) default.

## 3. The 4 consumption patterns

### 3.1 Use tokens directly (recommended)

```css
.my-thing {
  background: var(--panel);
  color: var(--ink);
  border: 1px solid var(--rule);
}
```

This is how [inversion-atlas's css](../../inversion-atlas/atlases/inversion/css/inversion.css)
works — single line at the top of the file: "Uses tokens from
atlas-core/css/tokens.css." Then every rule consumes them.

### 3.2 Local aliases on a page wrapper

When a page has a long history of using different variable names (the
core dashboard's `--fg / --muted / --bg-card / --border / --accent`),
alias them on the wrapper instead of rewriting every selector:

```css
.core-page {
  --fg:      var(--ink);
  --muted:   var(--ink-dim);
  --bg-card: var(--panel);
  --border:  var(--rule);
  --accent:  var(--accent-2);
}
```

See [`atlases/core/css/core_pages.css` §1](../atlases/core/css/core_pages.css).
Pattern used after rewiring 2026-05-20.

### 3.3 `color-mix()` for theme-derived tints

For semi-transparent backgrounds derived from a saturated status colour:

```css
.badge.contract-fail {
  background: color-mix(in srgb, var(--fail) 18%, transparent);
  color: var(--fail);
}
```

Works on both light and dark themes — the tint adapts to the page bg
because `transparent` blends with whatever is behind.

Used in `core_pages.css` for status badges, conversation warning banner,
action error block, selected-step focus ring. Browser support: Chrome
111+, Firefox 113+, Safari 16.2+ (i.e. modern only — the atlas requires
modern browsers anyway).

### 3.4 `filter: brightness()` for hover states

For primary-button hover where the background is already a saturated
accent:

```css
.btn-primary { background: var(--accent); }
.btn-primary:hover { filter: brightness(0.85); }
```

Beats hardcoding `#225a96` — works for any theme's accent value.

## 4. When to keep colours literal

Some colours should NOT be themed:

| category               | example tokens                          | why literal                                  |
|------------------------|-----------------------------------------|----------------------------------------------|
| Semantic status        | `--ok #2f855a`, `--fail #c53030`        | universally-recognised meaning; same on dark + light + academic |
| Per-pipeline chains    | `--chain-ngsrelate`, `--chain-mendelian`| pipeline identity; readable on all bg tones  |
| Status-pill class colors | `--st-result-ready`, `--st-blocked`   | per-class status; saturated enough for any bg |
| Translucent shadows    | `rgba(0,0,0,0.04)`                      | semi-transparent black blends with any bg     |

These live as literal hex values inside `.core-page` (or wherever they're
needed). Don't promote them to `tokens.css` — they're not theme-axes.

## 5. Audit checklist for new CSS

Before adding CSS to an atlas, check:

1. **Does this colour have a token equivalent?** If yes, use it. (`#1a1f26` → `var(--ink)`)
2. **Is this a derived tint of a status?** Use `color-mix(in srgb, var(--ok) 18%, transparent)`.
3. **Is this a hover/focus state?** Prefer `var(--panel-2)` for subtle hovers, `filter: brightness(0.85)` for accent buttons.
4. **Is this a semantic status colour?** If yes, keep literal (with a comment explaining why).
5. **Run the audit grep:** from the atlas root, `grep -n "#[0-9a-fA-F]\{3,6\}\|rgba(" atlases/<id>/css/*.css` — review every hex / rgba.

## 6. Per-atlas conventions

- **inversion-atlas** — consumes tokens directly. No local aliases. Long
  single file (`atlases/inversion/css/inversion.css`) covering all pages.
- **diversity-atlas, genome-atlas, relatedness-atlas** — same as inversion;
  domain-specific tokens (e.g. genome's `--ga-chrom-sat`) are HSL knobs,
  not theme-overrides.
- **population-atlas** — intentionally overrides `--accent` / `--good` /
  `--bad` with its own amber palette. Documented at top of
  `atlases/population/css/population.css`.
- **core atlas** — uses local aliases on `.core-page` (§3.2) for historical
  reasons; rewired 2026-05-20.

## 7. Adding a new theme

To add a 4th theme (e.g. "high-contrast" for accessibility):

1. Add `html[data-theme="high-contrast"] { ... }` block in `tokens.css`
   redefining every token that needs to change.
2. Append to `THEMES` array in
   [`core/shell_chrome.js`](../core/shell_chrome.js) — the cycle is
   `THEMES.indexOf(cur) + 1) % THEMES.length`.
3. Add `THEME_LABEL` entry so the toggle button text reads correctly.
4. Test against the inversion-atlas (most complex CSS) and core/inventory
   (most token-dependent page).

No per-atlas changes needed when tokens are consumed via §3.1.
