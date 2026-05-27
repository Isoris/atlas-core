// core/tree_layer_registry.js
// =====================================================================
// Tree-layer validation + typed-path resolution per SPEC_tree_layers_v1.md.
//
// Tree-layers live INSIDE per-atlas `registries/data/layers.registry.json`
// entries with `kind: "tree"`. This module doesn't load that file (the
// existing layers loader does); it provides the validator + the typed-
// path walker that `layer_router.js` consults at read time.
//
// Public exports:
//
//   validateTreeLayer(layerEntry, opts?) → string[]
//     Schema-shape + cross-reference validation per SPEC §7.
//     opts: { cohortsRegistry, workflowsRegistry }.
//     Returns [] when valid; otherwise an array of one-line error messages.
//
//   resolveTreePath(layerEntry, treePath) → resolvedPath
//     Walks the dot-separated treePath through layerEntry.tree, returns
//       { kind:'leaf', absPath, leaf_kind }       — explicit leaf
//       { kind:'dir',  absPath, node }            — directory (caller may list)
//       { kind:'pattern_match', absPath, leaf_kind } — pattern-dir's children fan-out
//     Throws InvalidTreePathError when the path doesn't map onto the tree.
//
//   walkTreePaths(layerEntry) → Iterator<{ path:string, node }>
//     Yields every leaf + dir-pattern node in the tree as
//     dot-separated paths. Used by docs / introspection.
//
//   InvalidTreePathError — thrown by resolveTreePath.
//
// Note: this module is path-resolution only. Actual file I/O + parsing
// belongs in layer_router.js (which calls fs.readFile + the leaf-kind
// parsers registry). That keeps tree_layer_registry runnable under Node
// for tests without pulling in atlas-server.
// =====================================================================

const VALID_LEAF_KINDS = new Set([
  'tsv', 'csv', 'json', 'jsonl', 'paf', 'bed',
  'fasta', 'fai', 'vcf', 'vcfgz', 'gff', 'bin',
]);

export class InvalidTreePathError extends Error {
  constructor(message, layerId, treePath) {
    super(message);
    this.name = 'InvalidTreePathError';
    this.layerId = layerId;
    this.treePath = treePath;
  }
}

// =====================================================================
// validation — SPEC §7
// =====================================================================

export function validateTreeLayer(layerEntry, opts) {
  const errors = [];
  const o = opts || {};
  if (!layerEntry || typeof layerEntry !== 'object') {
    return ['tree-layer: payload is not an object'];
  }
  if (layerEntry.kind !== 'tree') {
    errors.push(`tree-layer: kind must be 'tree' (got ${JSON.stringify(layerEntry.kind)})`);
  }
  if (typeof layerEntry.layer_id !== 'string' || !/^[a-zA-Z][a-zA-Z0-9_]*$/.test(layerEntry.layer_id)) {
    // Mixed case allowed for layer_ids (passA, passB are real-world bioinformatics
    // names); cohort_ids stay strict-lowercase elsewhere.
    errors.push(`tree-layer: bad layer_id ${JSON.stringify(layerEntry.layer_id)}`);
  }
  if (typeof layerEntry.label !== 'string' || layerEntry.label.length === 0) {
    errors.push(`tree-layer '${layerEntry.layer_id}': label missing or empty`);
  }
  if (typeof layerEntry.root !== 'string' || layerEntry.root.length === 0) {
    errors.push(`tree-layer '${layerEntry.layer_id}': root missing or empty`);
  }
  if (!layerEntry.tree || typeof layerEntry.tree !== 'object' || Array.isArray(layerEntry.tree)) {
    errors.push(`tree-layer '${layerEntry.layer_id}': tree missing or not an object`);
    return errors;   // can't recurse without a tree
  }

  // Optional cross-validation.
  if (layerEntry.cohort_id != null) {
    if (typeof layerEntry.cohort_id !== 'string' || !/^[a-z][a-z0-9_]*$/.test(layerEntry.cohort_id)) {
      errors.push(`tree-layer '${layerEntry.layer_id}': bad cohort_id ${JSON.stringify(layerEntry.cohort_id)}`);
    } else if (o.cohortsRegistry && Array.isArray(o.cohortsRegistry.cohorts)) {
      const known = new Set(o.cohortsRegistry.cohorts.map(c => c && c.cohort_id).filter(Boolean));
      if (!known.has(layerEntry.cohort_id)) {
        errors.push(`tree-layer '${layerEntry.layer_id}': cohort_id '${layerEntry.cohort_id}' is not in cohorts.registry.json`);
      }
    }
  }
  if (layerEntry.produced_by != null) {
    if (typeof layerEntry.produced_by !== 'string' || !/^[a-z][a-z0-9_]*$/.test(layerEntry.produced_by)) {
      errors.push(`tree-layer '${layerEntry.layer_id}': bad produced_by ${JSON.stringify(layerEntry.produced_by)}`);
    } else if (o.workflowsRegistry && Array.isArray(o.workflowsRegistry.workflows)) {
      const known = new Set(o.workflowsRegistry.workflows.map(w => w && w.workflow_id).filter(Boolean));
      if (!known.has(layerEntry.produced_by)) {
        errors.push(`tree-layer '${layerEntry.layer_id}': produced_by '${layerEntry.produced_by}' is not a registered workflow_id`);
      }
    }
  }

  // Recurse through the tree.
  _walkValidate(layerEntry.layer_id, '', layerEntry.tree, errors);
  return errors;
}

function _walkValidate(layerId, pathPrefix, treeObj, errors) {
  for (const [name, node] of Object.entries(treeObj)) {
    const here = pathPrefix ? `${pathPrefix}.${name}` : name;
    if (!node || typeof node !== 'object') {
      errors.push(`tree-layer '${layerId}': node at '${here}' is not an object`);
      continue;
    }
    if (node.kind === 'leaf') {
      if (!VALID_LEAF_KINDS.has(node.leaf_kind)) {
        errors.push(`tree-layer '${layerId}': leaf '${here}' has unknown leaf_kind ${JSON.stringify(node.leaf_kind)} (valid: ${[...VALID_LEAF_KINDS].sort().join(', ')})`);
      }
    } else if (node.kind === 'dir') {
      const hasChildren = node.children && typeof node.children === 'object';
      const hasPattern  = typeof node.children_pattern === 'string';
      if (hasChildren && hasPattern) {
        errors.push(`tree-layer '${layerId}': dir '${here}' has BOTH children and children_pattern (must be one or the other)`);
      } else if (!hasChildren && !hasPattern) {
        errors.push(`tree-layer '${layerId}': dir '${here}' has neither children nor children_pattern`);
      } else if (hasPattern) {
        if (!node.leaf_kind || !VALID_LEAF_KINDS.has(node.leaf_kind)) {
          errors.push(`tree-layer '${layerId}': pattern-dir '${here}' has missing/unknown leaf_kind ${JSON.stringify(node.leaf_kind)}`);
        }
        if (node.children_pattern.length === 0) {
          errors.push(`tree-layer '${layerId}': pattern-dir '${here}' has empty children_pattern`);
        }
      } else {
        // explicit children — recurse
        if (Object.keys(node.children).length === 0) {
          errors.push(`tree-layer '${layerId}': dir '${here}' has empty children`);
        } else {
          _walkValidate(layerId, here, node.children, errors);
        }
      }
    } else if (node.kind === 'tree_ref') {
      // SPEC §4 — nested tree-layers are flagged as "not allowed in v1" per the open
      // question's accepted resolution. Surface as a validation failure.
      errors.push(`tree-layer '${layerId}': node '${here}' uses 'tree_ref' kind which is not allowed in tree_layer v1 (see SPEC §4 open question resolution)`);
    } else {
      errors.push(`tree-layer '${layerId}': node '${here}' has unknown kind ${JSON.stringify(node.kind)} (valid: dir, leaf)`);
    }
  }
}

// =====================================================================
// typed-path resolution — SPEC §6
// =====================================================================

// Longest-prefix match against a children map. Returns
//   { key, consumed: <int> }
// where `key` is the child name (which may contain dots like
// `reciprocity_table.tsv`) and `consumed` is how many segments it covers.
// Returns null when no key matches.
function _matchLongestChild(childrenMap, parts, fromIndex) {
  if (!childrenMap) return null;
  const remaining = parts.slice(fromIndex).join('.');
  let best = null;
  for (const key of Object.keys(childrenMap)) {
    if (remaining === key || remaining.startsWith(key + '.')) {
      const consumed = key.split('.').length;
      if (best == null || consumed > best.consumed) {
        best = { key, consumed };
      }
    }
  }
  return best;
}

export function resolveTreePath(layerEntry, treePath) {
  if (!layerEntry || layerEntry.kind !== 'tree') {
    throw new InvalidTreePathError(
      'resolveTreePath: layerEntry is not a tree-layer',
      layerEntry && layerEntry.layer_id, treePath);
  }
  const root = (layerEntry.root || '').replace(/\/+$/, '');
  if (treePath == null || treePath === '') {
    return { kind: 'metadata', absPath: root, node: layerEntry.tree };
  }
  const parts = String(treePath).split('.');
  let node = layerEntry.tree;
  let pathSoFar = root;
  let i = 0;
  while (i < parts.length) {
    // At a tree-object level (top of layerEntry.tree, or a dir.children).
    // Use longest-prefix matching so explicit child names that contain dots
    // (e.g. 'reciprocity_table.tsv') resolve correctly.
    if (node && !node.kind && typeof node === 'object') {
      const m = _matchLongestChild(node, parts, i);
      if (m) {
        pathSoFar = pathSoFar + '/' + m.key;
        node = node[m.key];
        i += m.consumed;
        continue;
      }
    }
    // At a dir node — descend through children (longest-prefix) or pattern.
    if (node && node.kind === 'dir') {
      if (node.children) {
        const m = _matchLongestChild(node.children, parts, i);
        if (m) {
          pathSoFar = pathSoFar + '/' + m.key;
          node = node.children[m.key];
          i += m.consumed;
          continue;
        }
      }
      if (typeof node.children_pattern === 'string') {
        // Pattern dir — all remaining segments concatenate into the
        // single child filename. SPEC §6 example:
        //   '02_paf_passA.Cgar_h1_vs_Cmac_h1.paf' → that specific PAF.
        // Strict SPEC reading allows ONE child segment after a pattern
        // dir; we support multi-segment because real filenames contain
        // dots (e.g. 'Cgar_h1_vs_Cmac_h1.paf' is one segment after
        // splitting on '.'). Join them back to recover the filename.
        const filename = parts.slice(i).join('.');
        pathSoFar = pathSoFar + '/' + filename;
        return {
          kind: 'pattern_match',
          absPath: pathSoFar,
          leaf_kind: node.leaf_kind,
        };
      }
      throw new InvalidTreePathError(
        `tree path '${treePath}' segment '${parts[i]}' not found in dir at '${parts.slice(0, i).join('.')}'`,
        layerEntry.layer_id, treePath);
    }
    // Leaf with remaining path → can't descend into a leaf.
    if (node && node.kind === 'leaf') {
      throw new InvalidTreePathError(
        `tree path '${treePath}' descends past leaf at '${parts.slice(0, i).join('.')}'`,
        layerEntry.layer_id, treePath);
    }
    // Unknown shape.
    throw new InvalidTreePathError(
      `tree path '${treePath}' segment '${parts[i]}' not found`,
      layerEntry.layer_id, treePath);
  }
  // Reached the end of the path. Classify what we landed on.
  if (node && node.kind === 'leaf') {
    return { kind: 'leaf', absPath: pathSoFar, leaf_kind: node.leaf_kind };
  }
  if (node && node.kind === 'dir') {
    // Landing on a pattern-dir without a child segment → return dir
    // metadata; the caller decides whether to list children.
    return {
      kind: 'dir',
      absPath: pathSoFar,
      node,
      // children_pattern + leaf_kind surfaced for caller's convenience.
      children_pattern: typeof node.children_pattern === 'string' ? node.children_pattern : null,
      leaf_kind:        node.children_pattern ? node.leaf_kind : null,
    };
  }
  // Landing on a sub-tree object (children-of-dir or layerEntry.tree).
  return { kind: 'subtree', absPath: pathSoFar, node };
}

// =====================================================================
// path walker — used for introspection / docs
// =====================================================================

export function walkTreePaths(layerEntry) {
  if (!layerEntry || layerEntry.kind !== 'tree' || !layerEntry.tree) return [];
  const out = [];
  _walkCollect('', layerEntry.tree, out);
  return out;
}

function _walkCollect(pathPrefix, treeObj, out) {
  for (const [name, node] of Object.entries(treeObj)) {
    const here = pathPrefix ? `${pathPrefix}.${name}` : name;
    if (!node || typeof node !== 'object') continue;
    if (node.kind === 'leaf') {
      out.push({ path: here, node });
    } else if (node.kind === 'dir') {
      if (typeof node.children_pattern === 'string') {
        out.push({ path: here, node });   // pattern dirs are surfaced as leaves-by-pattern
      } else if (node.children && typeof node.children === 'object') {
        _walkCollect(here, node.children, out);
      }
    }
  }
}
