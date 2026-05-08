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
//   - binary  → fetch + arrayBuffer
//
// The router does not cache. Caching is the registry's job.
// =====================================================================

export class LayerRouter {

  // fields: optional Array<string>. Forwarded to parseDelimited for
  // tsv/csv. Ignored for json/binary (where column-level filtering
  // doesn't apply). Out-of-list columns are dropped at parse time so
  // wide files don't waste RAM. See parseDelimited for semantics.
  async fetchFile(path, format = 'json', fields = null) {
    if (format === 'json')   return this._fetchJson(path);
    if (format === 'tsv')    return this._fetchDelimited(path, '\t', fields);
    if (format === 'csv')    return this._fetchDelimited(path, ',', fields);
    if (format === 'binary') return this._fetchBinary(path);
    throw new Error(`LayerRouter.fetchFile: unknown format '${format}'`);
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
