// core/layer_router.js
// =====================================================================
// Routes a layer-resolution request to its file source.
//
// Path templating happens BEFORE the router sees the entry; the
// registry calls templateFill() first, so the router gets a literal
// path and a format hint.
//
// Formats supported:
//   - json    → fetch + JSON.parse
//   - tsv     → fetch + parseTsv
//   - csv     → fetch + parseCsv
//   - text    → fetch + raw string (caller parses; used for bespoke
//               formats like ANGSD .est.ml — two whitespace-separated
//               values on one line, no header)
//   - binary  → fetch + arrayBuffer
//
// Tree-layer extension (SPEC_tree_layers_v1):
//   - readTreePath(layerEntry, treePath) — resolves the typed dot-path
//     through layerEntry.tree via core/tree_layer_registry.js, then
//     dispatches to fetchFile() with the leaf_kind mapped to a format.
//     Leaf + pattern_match return parsed data; metadata / subtree /
//     dir return structural objects (no I/O). Pattern-dir bulk-read
//     (returning a Map of all matches) is deferred to v2 — needs an
//     atlas-server directory-listing endpoint that doesn't exist yet.
//
// The router does not cache. Caching is the registry's job.
// =====================================================================

import { resolveTreePath } from './tree_layer_registry.js';

// Leaf-kind → fetchFile format mapping. SPEC §5 lists the leaf kinds
// and how they parse; this table picks the closest existing format for
// each. Streamed kinds (fasta/vcf/vcfgz) are out of v1 scope per
// SPEC §12 — they throw a clear error if requested.
//
// `headerless: true` formats are tab-delimited but lack a header row
// (PAF, BED, GFF, FAI). For those, readTreePath bypasses fetchFile and
// calls parseDelimited directly with {hasHeader: false} so columns are
// synthesized as col_0, col_1, ... — caller maps those to format-specific
// field names (PAF has a canonical 12-column spec + tagged extras, etc.).
const _LEAF_KIND_TO_FORMAT = {
  tsv:    { format: 'tsv' },
  csv:    { format: 'csv' },
  paf:    { format: 'tsv', headerless: true },   // PAF: 12 spec cols + tagged extras
  bed:    { format: 'tsv', headerless: true },   // BED: 3+9 cols
  gff:    { format: 'tsv', headerless: true },   // GFF: 9 cols
  fai:    { format: 'tsv', headerless: true },   // FASTA index: name\tlength\toffset\tlinebases\tlinewidth
  json:   { format: 'json' },
  jsonl:  { format: 'text' },                    // caller .split('\n').map(JSON.parse) — keep router simple
  bin:    { format: 'binary' },
  // fasta / vcf / vcfgz: streamed leaves — caller must use a streaming
  // reader (out of v1 scope; the loader throws on these).
};

export class LayerRouter {

  // fields: optional Array<string>. Forwarded to parseDelimited for
  // tsv/csv. Ignored for json/text/binary (where column-level filtering
  // doesn't apply). Out-of-list columns are dropped at parse time so
  // wide files don't waste RAM. See parseDelimited for semantics.
  async fetchFile(path, format = 'json', fields = null) {
    if (format === 'json')   return this._fetchJson(path);
    if (format === 'tsv')    return this._fetchDelimited(path, '\t', fields);
    if (format === 'csv')    return this._fetchDelimited(path, ',', fields);
    if (format === 'text')   return this._fetchText(path);
    if (format === 'binary') return this._fetchBinary(path);
    throw new Error(`LayerRouter.fetchFile: unknown format '${format}'`);
  }

  async _fetchText(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`LayerRouter: GET ${path} → HTTP ${resp.status}`);
    return resp.text();
  }

  async _fetchJson(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`LayerRouter: GET ${path} → HTTP ${resp.status}`);
    return resp.json();
  }

  async _fetchDelimited(path, sep, fields = null) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`LayerRouter: GET ${path} → HTTP ${resp.status}`);

    // Handle .gz transparently if available. fetch() with response
    // headers Content-Encoding: gzip is auto-decompressed by the browser.
    // For static .tsv.gz files served with text/plain, we'd need a
    // gunzip shim — out of scope for v1.
    const text = await resp.text();
    return parseDelimited(text, sep, fields);
  }

  async _fetchBinary(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`LayerRouter: GET ${path} → HTTP ${resp.status}`);
    return resp.arrayBuffer();
  }

  // Typed read into a tree-layer (SPEC_tree_layers_v1 §6).
  //   layerEntry — the tree-layer entry (kind:'tree', root, tree)
  //   treePath   — dot-separated path through layerEntry.tree. null/'' →
  //                metadata read (returns the tree object, no I/O).
  //
  // Returns one of:
  //   - parsed leaf data    (kind:'leaf' / 'pattern_match')
  //   - {kind, node, ...}   (kind:'metadata' / 'subtree' / 'dir')
  //
  // Pattern-dir bulk-read (treePath stops at a pattern dir, expecting a
  // Map of {filename → parsed}) is NOT implemented — needs an
  // atlas-server directory-listing endpoint. The current behaviour
  // returns the dir metadata so the caller knows what to fetch.
  async readTreePath(layerEntry, treePath, opts) {
    const o = opts || {};
    const resolved = resolveTreePath(layerEntry, treePath);

    // Structural results — no I/O.
    if (resolved.kind === 'metadata' || resolved.kind === 'subtree'
        || resolved.kind === 'dir') {
      return resolved;
    }

    // Leaf or pattern-match — fetch the file. Both have absPath + leaf_kind.
    if (resolved.kind === 'leaf' || resolved.kind === 'pattern_match') {
      const leafKind = resolved.leaf_kind;
      const mapping = _LEAF_KIND_TO_FORMAT[leafKind];
      if (!mapping) {
        throw new Error(
          `LayerRouter.readTreePath: leaf_kind '${leafKind}' is not supported in v1 `
          + `(streamed kinds fasta/vcf/vcfgz need a streaming reader; see SPEC §12). `
          + `Path: ${resolved.absPath}`
        );
      }
      // Allow caller to override the abs-path prefix (e.g. atlas-server
      // mounts files under /file/<root>/...). Default is the raw absPath
      // built from layerEntry.root + tree path segments.
      const prefix = (typeof o.urlPrefix === 'string') ? o.urlPrefix.replace(/\/+$/, '') + '/' : '';
      const url = prefix + resolved.absPath.replace(/^\/+/, '');
      const fields = (mapping.format === 'tsv' || mapping.format === 'csv') ? o.fields : null;
      // Headerless formats bypass fetchFile (which assumes hasHeader:true
      // via parseDelimited's default) and call the parser directly.
      if (mapping.headerless) {
        const text = await this._fetchText(url);
        return parseDelimited(text, '\t', fields, { hasHeader: false });
      }
      return this.fetchFile(url, mapping.format, fields);
    }

    throw new Error(`LayerRouter.readTreePath: unknown resolution kind '${resolved.kind}'`);
  }
}

// ---------------------------------------------------------------------
// Pure helper, exported for tests.
//
// Returns an array of objects keyed by header columns.
// First non-empty, non-comment line is the header (when opts.hasHeader,
// the default). With opts.hasHeader === false, every non-empty,
// non-comment line is a data row and column names are synthesized as
// 'col_0', 'col_1', ... — used for headerless tool outputs like
// NGSadmix .qopt.
// Comment lines (starting with '#') are skipped.
// Blank lines are skipped.
//
// Numeric coercion: if every non-empty value in a column parses as a
// finite number, the whole column is numeric. Otherwise string.
// (This matches what the legacy atlas does for precomp TSVs.)
//
// fieldsAllowList: optional Array<string>. When provided, the parser
// only emits the listed columns in each row object. Columns not in
// the list are skipped (saves RAM on wide files like ngsRelate output
// with 23 columns when the analysis only needs 5). Numeric coercion
// is still computed per-column but only applied to the kept columns.
// Unknown column names in the allow-list are silently ignored.
//
// sep: either a string separator ('\t', ',') OR the sentinel string
// 'whitespace' which splits on /\s+/ (one-or-more whitespace) — used
// for tool outputs like NGSadmix .qopt that may emit either spaces or
// tabs depending on version/locale.
//
// opts.hasHeader (default true): when false, no header row is consumed
// and synthesized column names 'col_0'..'col_{N-1}' are used instead.
// Width N is determined by the first data row.
// ---------------------------------------------------------------------

export function parseDelimited(text, sep, fieldsAllowList = null, opts = {}) {
  const hasHeader = (opts.hasHeader === undefined) ? true : !!opts.hasHeader;
  const splitFn = (sep === 'whitespace')
    ? (line) => line.split(/\s+/).filter((s) => s.length > 0)
    : (line) => line.split(sep);

  const lines = text.split(/\r?\n/);
  const rows = [];
  let header = null;

  // If we have an allow-list, build a Set for O(1) membership checks.
  // null means "keep all columns" (legacy behavior).
  const allowSet = fieldsAllowList ? new Set(fieldsAllowList) : null;

  for (const line of lines) {
    if (line.length === 0) continue;
    if (line.startsWith('#')) continue;
    const fields = splitFn(line);
    if (fields.length === 0) continue;
    if (header === null) {
      if (hasHeader) {
        header = fields;
        continue;
      }
      // Headerless: synthesize column names from the width of this row.
      // Subsequent rows shorter than this width will get '' for missing.
      header = fields.map((_, i) => `col_${i}`);
      // Fall through — this row is data, not header.
    }
    const row = {};
    for (let i = 0; i < header.length; i++) {
      const colName = header[i];
      if (allowSet && !allowSet.has(colName)) continue;
      row[colName] = fields[i] === undefined ? '' : fields[i];
    }
    rows.push(row);
  }

  if (header === null) return [];

  // Coerce numeric columns. Only for columns we actually kept.
  const colsToCoerce = allowSet
    ? header.filter((c) => allowSet.has(c))
    : header;

  for (const col of colsToCoerce) {
    let allNumeric = true;
    for (const row of rows) {
      const v = row[col];
      if (v === '' || v === 'NA' || v === 'NaN') continue;
      const n = Number(v);
      if (!Number.isFinite(n)) { allNumeric = false; break; }
    }
    if (allNumeric) {
      for (const row of rows) {
        const v = row[col];
        if (v === '' || v === 'NA' || v === 'NaN') {
          row[col] = null;
        } else {
          row[col] = Number(v);
        }
      }
    }
  }

  return rows;
}
