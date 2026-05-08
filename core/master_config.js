// core/master_config.js
// =====================================================================
// Loads master_config.yaml (or master_config.json) at startup and
// hands the registry a typed object describing roots, species, server
// settings, etc.
//
// The config contract is documented in toolkit_registries/MASTER_CONFIG.md
// and validated against toolkit_registries/schemas/registry_schemas/
// master_config.schema.json. This module is the runtime side: discovery,
// parsing, ${roots.X.path} substitution, sanity checks.
//
// Discovery order (matches MASTER_CONFIG.md §"File location and discovery"):
//   1. window.ATLAS_MASTER_CONFIG override URL (test / multi-config dev).
//   2. ./master_config.json   — the JSON form, if present (cheap, no parser).
//   3. ./master_config.yaml   — the YAML form, parsed by the embedded reader.
//   4. ./master_config.example.yaml — last-resort example with a warning.
//   5. null — engine continues with no master_config; layers that declare
//      `root: <name>` will fail at resolve time, layers using bare `path:`
//      keep working via the atlas-relative fallback in registry_core.
//
// The registry is fault-tolerant: a missing master_config is NOT a boot
// error. It only matters for layers that opt in to `root: <name>`.
// =====================================================================

/**
 * Load the master config from the workspace root.
 * Returns the parsed object, or null if no config file is present.
 * Throws only on parse / validation errors — missing file is normal.
 */
export async function loadMasterConfig({ baseUrl = '' } = {}) {
  const candidates = [];
  if (typeof window !== 'undefined' && window.ATLAS_MASTER_CONFIG) {
    candidates.push({ url: window.ATLAS_MASTER_CONFIG, kind: _guessKind(window.ATLAS_MASTER_CONFIG) });
  }
  candidates.push(
    { url: baseUrl + 'master_config.json',         kind: 'json' },
    { url: baseUrl + 'master_config.yaml',         kind: 'yaml' },
    { url: baseUrl + 'master_config.example.yaml', kind: 'yaml', isExample: true },
  );

  for (const cand of candidates) {
    const text = await _fetchTextOrNull(cand.url);
    if (text === null) continue;
    let cfg;
    try {
      cfg = (cand.kind === 'json') ? JSON.parse(text) : parseYamlSubset(text);
    } catch (e) {
      throw new Error(`master_config: failed to parse ${cand.url}: ${e.message}`);
    }
    cfg = resolveSubstitutions(cfg);
    validateMasterConfig(cfg, cand.url);
    if (cand.isExample) {
      console.warn(
        `master_config: using example file ${cand.url}. ` +
        `Copy it to master_config.yaml (or .json) and edit roots[].path for this machine.`
      );
    }
    cfg._source_url = cand.url;
    return cfg;
  }
  return null;
}

async function _fetchTextOrNull(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    return await r.text();
  } catch {
    return null;
  }
}

function _guessKind(url) {
  if (/\.json($|\?)/i.test(url)) return 'json';
  return 'yaml';
}

// ---------------------------------------------------------------------
// Validation — minimal at runtime; the JSON Schema in toolkit_registries
// is the canonical contract. Here we just check the shape the registry
// actually depends on (atlas + roots) and surface obvious mistakes early.
// ---------------------------------------------------------------------

export function validateMasterConfig(cfg, srcUrl = '<inline>') {
  if (!cfg || typeof cfg !== 'object' || Array.isArray(cfg)) {
    throw new Error(`master_config(${srcUrl}): top level must be an object`);
  }
  if (!cfg.atlas || typeof cfg.atlas !== 'object') {
    throw new Error(`master_config(${srcUrl}): missing required 'atlas' section`);
  }
  if (!cfg.roots || typeof cfg.roots !== 'object') {
    throw new Error(`master_config(${srcUrl}): missing required 'roots' section`);
  }
  for (const [name, entry] of Object.entries(cfg.roots)) {
    if (!entry || typeof entry !== 'object') {
      throw new Error(`master_config(${srcUrl}): root '${name}' must be an object`);
    }
    if (typeof entry.path !== 'string' || entry.path.length === 0) {
      throw new Error(`master_config(${srcUrl}): root '${name}' missing 'path'`);
    }
    if (entry.role !== undefined &&
        !['samples', 'intervals', 'evidence', 'results'].includes(entry.role)) {
      throw new Error(
        `master_config(${srcUrl}): root '${name}' has invalid role '${entry.role}'. ` +
        `Must be one of samples/intervals/evidence/results.`
      );
    }
  }
  if (cfg.species !== undefined) {
    if (!Array.isArray(cfg.species)) {
      throw new Error(`master_config(${srcUrl}): 'species' must be an array`);
    }
    for (const sp of cfg.species) {
      if (!sp || !sp.id) {
        throw new Error(`master_config(${srcUrl}): species entry missing 'id'`);
      }
    }
  }
  return true;
}

// ---------------------------------------------------------------------
// ${roots.X.path} substitution — resolved once at load time, with
// cycle detection. Per MASTER_CONFIG.md §"Variable substitution".
// ---------------------------------------------------------------------

const SUBST_RE = /\$\{([^}]+)\}/g;

export function resolveSubstitutions(cfg) {
  // Walk every string value and replace ${path.to.value} with the
  // value at that path inside `cfg`. Cycles throw with the cycle path.
  const memo = new Map();
  return _walk(cfg, [], memo, cfg);
}

function _walk(node, keyPath, memo, root) {
  if (typeof node === 'string') {
    return _resolveString(node, keyPath, memo, root);
  }
  if (Array.isArray(node)) {
    return node.map((item, i) => _walk(item, keyPath.concat(i), memo, root));
  }
  if (node && typeof node === 'object') {
    const out = {};
    for (const k of Object.keys(node)) {
      out[k] = _walk(node[k], keyPath.concat(k), memo, root);
    }
    return out;
  }
  return node;
}

function _resolveString(str, keyPath, memo, root) {
  if (!str.includes('${')) return str;
  const cacheKey = str;
  if (memo.has(cacheKey)) {
    const v = memo.get(cacheKey);
    if (v === '__resolving__') {
      throw new Error(
        `master_config: substitution cycle detected at '${keyPath.join('.')}': '${str}'`
      );
    }
    return v;
  }
  memo.set(cacheKey, '__resolving__');
  const out = str.replace(SUBST_RE, (_, ref) => {
    const v = _lookupPath(root, ref);
    if (v === undefined) {
      throw new Error(
        `master_config: '\${${ref}}' in '${keyPath.join('.')}' refers to nothing`
      );
    }
    if (typeof v === 'string') {
      return _resolveString(v, ref.split('.'), memo, root);
    }
    return String(v);
  });
  memo.set(cacheKey, out);
  return out;
}

function _lookupPath(obj, dotted) {
  const parts = dotted.split('.');
  let cur = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = cur[p];
  }
  return cur;
}

// ---------------------------------------------------------------------
// Root resolution — the registry calls this to get a fully-formed
// directory path for a given root name, given the active state.
//
// `args` may carry { species_id }; otherwise it falls back to
// state.shared.activeSpecies. Roots with `species_scoped: true` get
// {species_id} substituted; non-scoped roots ignore species entirely.
// ---------------------------------------------------------------------

export function resolveRootPath(masterConfig, rootName, args = {}, state = null) {
  if (!masterConfig || !masterConfig.roots) {
    throw new Error(
      `master_config: layer references root '${rootName}' but no master_config is loaded. ` +
      `Drop a master_config.yaml at the workspace root or rewrite the layer to use 'path:' instead of 'root:'.`
    );
  }
  const entry = masterConfig.roots[rootName];
  if (!entry) {
    throw new Error(
      `master_config: layer references unknown root '${rootName}'. ` +
      `Known roots: ${Object.keys(masterConfig.roots).sort().join(', ')}`
    );
  }
  let p = entry.path;
  if (entry.species_scoped) {
    const speciesId =
      (args && args.species_id) ||
      (state && state.shared && state.shared.activeSpecies) ||
      _firstActiveSpeciesId(masterConfig);
    if (!speciesId) {
      throw new Error(
        `master_config: root '${rootName}' is species_scoped but no species_id resolved ` +
        `(no args.species_id, no state.shared.activeSpecies, no master_config.species[].active=true).`
      );
    }
    p = p.replace(/\{species_id\}/g, speciesId);
  }
  // Strip a leading "./" — relative to workspace root means relative
  // to whatever the document root the shell is served from. Browsers
  // resolve against the page URL, which is exactly what we want for a
  // workspace-relative path.
  if (p.startsWith('./')) p = p.slice(2);
  return p;
}

function _firstActiveSpeciesId(masterConfig) {
  if (!Array.isArray(masterConfig.species)) return null;
  const active = masterConfig.species.find((s) => s.active === true);
  if (active) return active.id;
  return masterConfig.species[0]?.id || null;
}

// =====================================================================
// Minimal YAML parser
//
// Supports the SUBSET of YAML the master_config example uses:
//   - block mappings (key: value, key: <indented-block>)
//   - block sequences (- item, - <indented-mapping>)
//   - scalars: plain, single-quoted, double-quoted (no escapes beyond \", \\, \n, \t)
//   - literals: true / false / null / ~ / numbers / integers / floats
//   - comments (# to end of line)
//   - blank lines
//
// Does NOT support:
//   - flow style ({...}, [...])
//   - anchors / aliases (&id, *id)
//   - tags (!!str, !!float)
//   - multiline scalars (| or >)
//   - document separators (---, ...)
//   - multiple documents per file
//
// The master_config.example.yaml uses none of those, so this is fine.
// If the user adds advanced YAML features, validation will throw with
// the specific line — they can then drop a .json instead, or convert.
// =====================================================================

export function parseYamlSubset(text) {
  // Pre-process: strip line comments and trailing whitespace, but preserve
  // # inside quoted strings (a basic state machine on each line).
  const rawLines = text.split(/\r?\n/);
  const lines = [];
  for (let i = 0; i < rawLines.length; i++) {
    const stripped = _stripComment(rawLines[i]).replace(/\s+$/, '');
    lines.push({ raw: stripped, lineno: i + 1 });
  }
  // Drop fully blank lines for the parser (track lineno on the rest).
  const nonBlank = lines.filter((l) => l.raw.length > 0);
  const ctx = { lines: nonBlank, idx: 0 };
  // The top level is always a block mapping (master_config) or empty.
  if (ctx.lines.length === 0) return {};
  return _parseBlock(ctx, 0);
}

function _stripComment(line) {
  let inS = false, inD = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (!inD && c === "'") inS = !inS;
    else if (!inS && c === '"') inD = !inD;
    else if (!inS && !inD && c === '#') return line.slice(0, i);
  }
  return line;
}

function _indent(line) {
  let i = 0;
  while (i < line.length && line[i] === ' ') i++;
  return i;
}

// Parse a block (mapping or sequence) at the given indent. Stops when
// the next line is at strictly less indent. Decides "mapping vs sequence"
// from whether the first content line at this indent starts with "- ".
function _parseBlock(ctx, indent) {
  const first = ctx.lines[ctx.idx];
  if (!first) return null;
  const txt = first.raw.slice(indent);
  if (txt.startsWith('- ') || txt === '-') {
    return _parseSequence(ctx, indent);
  }
  return _parseMapping(ctx, indent);
}

function _parseMapping(ctx, indent) {
  const out = {};
  while (ctx.idx < ctx.lines.length) {
    const line = ctx.lines[ctx.idx];
    const lineIndent = _indent(line.raw);
    if (lineIndent < indent) break;
    if (lineIndent > indent) {
      throw new Error(`yaml line ${line.lineno}: unexpected extra indent`);
    }
    const body = line.raw.slice(indent);
    // Match "key:" or "key: value" — the key is non-empty and must contain a colon.
    const m = body.match(/^([^:#]+?)\s*:(?:\s+(.*))?$/);
    if (!m) {
      throw new Error(`yaml line ${line.lineno}: expected 'key: value', got '${body}'`);
    }
    const key = _stripQuotes(m[1].trim());
    const tail = m[2] !== undefined ? m[2].trim() : '';
    ctx.idx++;
    if (tail.length > 0) {
      out[key] = _parseScalar(tail);
    } else {
      // Look at next non-blank line; if its indent > this indent, it's a child block.
      const next = ctx.lines[ctx.idx];
      if (next && _indent(next.raw) > indent) {
        out[key] = _parseBlock(ctx, _indent(next.raw));
      } else {
        out[key] = null;
      }
    }
  }
  return out;
}

function _parseSequence(ctx, indent) {
  const out = [];
  while (ctx.idx < ctx.lines.length) {
    const line = ctx.lines[ctx.idx];
    const lineIndent = _indent(line.raw);
    if (lineIndent < indent) break;
    if (lineIndent > indent) {
      throw new Error(`yaml line ${line.lineno}: unexpected extra indent in sequence`);
    }
    const body = line.raw.slice(indent);
    if (!body.startsWith('-')) break;
    const tail = body.slice(1).replace(/^\s+/, '');
    ctx.idx++;
    if (tail.length === 0) {
      // Pure "-" line; the value is the indented child block.
      const next = ctx.lines[ctx.idx];
      if (next && _indent(next.raw) > indent) {
        out.push(_parseBlock(ctx, _indent(next.raw)));
      } else {
        out.push(null);
      }
    } else if (tail.includes(':') && !tail.startsWith('"') && !tail.startsWith("'")) {
      // "- key: value" — start of an inline mapping. Parse it (and any
      // continuation lines at deeper indent) as a single mapping entry.
      // Implementation: rewind one line, replacing "- " with "  " so the
      // mapping parser sees a regular mapping at indent+2.
      const newIndent = indent + 2;
      // Synthesise a virtual line where "- " is replaced with "  ".
      ctx.idx--;
      const fixed = ' '.repeat(newIndent) + line.raw.slice(indent + 2);
      const savedRaw = line.raw;
      ctx.lines[ctx.idx] = { ...line, raw: fixed };
      const mapping = _parseMapping(ctx, newIndent);
      // Restore the original line (in case re-walked, though we don't).
      ctx.lines[ctx.idx - 1] = { ...line, raw: savedRaw };
      out.push(mapping);
    } else {
      out.push(_parseScalar(tail));
    }
  }
  return out;
}

function _parseScalar(s) {
  if (s === '' || s === '~' || s === 'null' || s === 'Null' || s === 'NULL') return null;
  if (s === 'true'  || s === 'True'  || s === 'TRUE')  return true;
  if (s === 'false' || s === 'False' || s === 'FALSE') return false;
  if (s.startsWith('"') && s.endsWith('"') && s.length >= 2) {
    return s.slice(1, -1)
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, '\t')
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, '\\');
  }
  if (s.startsWith("'") && s.endsWith("'") && s.length >= 2) {
    return s.slice(1, -1).replace(/''/g, "'");
  }
  // Number?
  if (/^-?\d+$/.test(s)) {
    const n = Number(s);
    if (Number.isFinite(n)) return n;
  }
  if (/^-?\d*\.\d+([eE][-+]?\d+)?$/.test(s) || /^-?\d+[eE][-+]?\d+$/.test(s)) {
    const n = Number(s);
    if (Number.isFinite(n)) return n;
  }
  return s;
}

function _stripQuotes(s) {
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1);
  }
  return s;
}
