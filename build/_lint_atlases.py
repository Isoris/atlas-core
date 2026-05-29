#!/usr/bin/env python3
"""
Static lint pass across every atlas repo on Desktop.

Checks:
  1. Each manifest.json parses as JSON.
  2. Every page's fragment + module paths exist on disk.
  3. Every manifest.registries.* path exists and is valid JSON.
  4. Stylesheet paths exist.
  5. Cross-atlas imports resolve: import "X.layer_id" must match a declared
     layer/operation in atlas X's layers.registry.json / operations.registry.json.
  6. Cross-atlas exports match what's actually in this atlas's layers.registry.json.
  7. cohorts.registry.json producer entries cross-check against each atlas's
     declared layers.

Pure read-only — never edits anything. Prints a finding per issue.
"""

import json, io, os, sys
from collections import defaultdict

DESKTOP = r"c:\Users\quent\Desktop"
ATLAS_DIRS = [
    "atlas-core/atlases/core",
    "cross-species-atlas/atlases/cross-species",
    "diversity-atlas/atlases/diversity",
    "evolution-atlas/atlases/evolution",
    "genome-atlas/atlases/genome",
    "heterozygosity-atlas/atlases/heterozygosity",
    "inversion-atlas/atlases/inversion",
    "loads-atlas/atlases/loads",
    "meiosis-atlas/atlases/meiosis",
    "pods-atlas/atlases/pods",
    "popstats-atlas/atlases/popstats",
    "population-atlas/atlases/population",
    "relatedness-atlas/atlases/relatedness",
]

# Each atlas package lives at <repo>/atlases/<id>/.  When assemble.sh runs
# it copies everything into atlas-workspace/atlases/<id>/.  For path
# resolution we treat the atlas-package root (the "atlases/<id>" parent,
# i.e. <repo>/) as the workspace root proxy: paths like
# "atlases/<id>/pages/..." resolve relative to that.

def load_json(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def safe_load(path):
    try: return load_json(path), None
    except Exception as e: return None, str(e)

findings = []
def fnd(severity, atlas, msg):
    findings.append((severity, atlas, msg))

# Index of every declared layer/operation, keyed by atlas_id.
declared_layers = defaultdict(set)
declared_operations = defaultdict(set)
manifest_by_atlas = {}
atlas_root_by_id = {}        # atlas_id -> Desktop/<repo>/ (workspace-equivalent root)

for atlas_subpath in ATLAS_DIRS:
    atlas_dir = os.path.join(DESKTOP, atlas_subpath.replace("/", os.sep))
    manifest_path = os.path.join(atlas_dir, "manifest.json")
    mf, err = safe_load(manifest_path)
    if err:
        fnd("ERR", atlas_subpath, f"manifest.json: {err}")
        continue
    atlas_id = mf.get("atlas_id", "?")
    manifest_by_atlas[atlas_id] = mf

    # atlas_id "cross-species" lives at "cross-species-atlas/atlases/cross-species/" —
    # i.e. parent.parent of atlas_dir is the workspace-equivalent root.
    workspace_root = os.path.dirname(os.path.dirname(atlas_dir))
    atlas_root_by_id[atlas_id] = workspace_root

    # Index declared layers + operations (load registry files)
    regs = mf.get("registries", {}) or {}
    for kind, path_rel in regs.items():
        full = os.path.join(workspace_root, path_rel.replace("/", os.sep))
        if not os.path.isfile(full):
            fnd("ERR", atlas_id, f"registries.{kind}: file not found at {path_rel}")
            continue
        reg, e = safe_load(full)
        if e:
            fnd("ERR", atlas_id, f"registries.{kind} parse: {e}")
            continue
        # Find the layers/operations array or dict
        if kind == "layers":
            arr = reg.get("layers")
            if isinstance(arr, list):
                for entry in arr:
                    if isinstance(entry, dict):
                        lid = entry.get("layer_id") or entry.get("name") or entry.get("id")
                        if lid: declared_layers[atlas_id].add(lid)
            elif isinstance(arr, dict):
                for lid in arr.keys():
                    if not lid.startswith("_"): declared_layers[atlas_id].add(lid)
        elif kind == "operations":
            arr = reg.get("operations")
            if isinstance(arr, list):
                for entry in arr:
                    if isinstance(entry, dict):
                        oid = entry.get("op_id") or entry.get("name") or entry.get("id")
                        if oid: declared_operations[atlas_id].add(oid)
            elif isinstance(arr, dict):
                for oid in arr.keys():
                    if not oid.startswith("_"): declared_operations[atlas_id].add(oid)

    # Page fragment + module + stylesheet path checks moved to a second pass
    # (after all atlases are indexed) so cross-atlas path resolution works.
    pass

# Page-path check (second pass — cross-atlas paths need ALL atlases indexed first)
# 2026-05-24: cross-atlas page fragments are allowed. When a path starts with
# `atlases/<other_atlas_id>/...` the file lives in that OTHER atlas's repo
# (e.g. cross-species's `synteny_free` page reuses
# atlases/genome/pages/comparative/page_synteny.html). At assemble time both
# atlases land in atlas-workspace/atlases/ as siblings; the lint follows the
# cross-atlas reference by looking up the foreign atlas's repo root.
def _resolve_page_path(v, owner_root):
    if not v or not v.startswith("atlases/"):
        return os.path.join(owner_root, (v or "").replace("/", os.sep))
    parts = v.split("/", 3)  # ['atlases', '<other_id>', ...]
    if len(parts) < 3:
        return os.path.join(owner_root, v.replace("/", os.sep))
    other_id = parts[1]
    other_root = atlas_root_by_id.get(other_id)
    if other_root:
        return os.path.join(other_root, v.replace("/", os.sep))
    return os.path.join(owner_root, v.replace("/", os.sep))

for atlas_id, mf in manifest_by_atlas.items():
    workspace_root = atlas_root_by_id.get(atlas_id)
    if not workspace_root: continue
    for page in mf.get("pages", []):
        for k in ("fragment", "module"):
            v = page.get(k)
            if not v: continue
            other_id = v.split("/", 3)[1] if v.startswith("atlases/") and v.count("/") >= 2 else atlas_id
            full = _resolve_page_path(v, workspace_root)
            if not os.path.isfile(full):
                severity = "WARN" if other_id != atlas_id else "ERR"
                where    = f" (cross-atlas to {other_id}-atlas)" if other_id != atlas_id else ""
                fnd(severity, atlas_id, f"page '{page.get('id')}' missing {k}: {v}{where}")
    for sheet in (mf.get("stylesheets") or []):
        full = _resolve_page_path(sheet, workspace_root)
        if not os.path.isfile(full):
            fnd("ERR", atlas_id, f"stylesheet not found: {sheet}")

# Cross-atlas import + export check (third pass — needs all atlases indexed)
for atlas_id, mf in manifest_by_atlas.items():
    cx = mf.get("cross_atlas") or {}
    for imp in (cx.get("imports") or []):
        layer = imp.get("layer", "")
        producer = imp.get("from", "")
        # Strip <producer>. prefix if present
        bare = layer.split(".", 1)[1] if "." in layer else layer
        # Layer may be a layer OR an op
        if (producer in declared_layers and bare in declared_layers[producer]) or \
           (producer in declared_operations and bare in declared_operations[producer]):
            continue
        fnd("WARN", atlas_id, f"cross_atlas.import '{layer}' from '{producer}' is not declared in producer's layers/operations registry")

    for exp in (cx.get("exports") or []):
        layer = exp.get("layer", "")
        bare = layer.split(".", 1)[1] if "." in layer else layer
        if bare in declared_layers.get(atlas_id, set()) or bare in declared_operations.get(atlas_id, set()):
            continue
        fnd("WARN", atlas_id, f"cross_atlas.export '{layer}' is not declared in this atlas's layers/operations registry")

# Orphan-root check intentionally removed 2026-05-23 after a brief trial.
# It produced ~13 warnings, most of which were false positives:
#   - server-side-only roots (beagle, cohort_dosage, reference, ...) read by
#     Python endpoints not by atlas layers — legitimately unreferenced
#     from layers.registry.json but still required;
#   - roots reserved for planned-but-not-yet-landed layers (mds_*, per_chrom_*);
#   - the one true orphan (genome_te_density) was already flagged manually
#     in master_config.yaml with a 2026-Q3 cleanup deadline.
# The noise destroyed the "0 warnings = ship-ready" signal that the rest
# of this lint enforces. Re-add as an INFO-level check (not WARN) if the
# need recurs; for now, audit master_config.yaml manually when it grows.

# cohorts.registry.json cross-check
cohorts_path = os.path.join(DESKTOP, "atlas-core", "cohorts.registry.json")
cohorts, e = safe_load(cohorts_path)
if e:
    fnd("ERR", "atlas-core", f"cohorts.registry.json: {e}")
else:
    producers = cohorts.get("producers") or {}
    for layer_key, meta in producers.items():
        if not isinstance(meta, dict): continue
        atlas_id = meta.get("atlas_id", "")
        bare = layer_key.split(".", 1)[1] if "." in layer_key else layer_key
        if bare in declared_layers.get(atlas_id, set()) or bare in declared_operations.get(atlas_id, set()):
            continue
        fnd("WARN", "cohorts.registry", f"producer '{layer_key}' attributes to '{atlas_id}' but no such layer/op declared there")

# Output
print("="*72)
print("ATLAS LINT REPORT")
print("="*72)
print(f"Atlases scanned: {len(manifest_by_atlas)}")
print(f"Layers indexed:     {sum(len(v) for v in declared_layers.values())}")
print(f"Operations indexed: {sum(len(v) for v in declared_operations.values())}")
print(f"Findings: {len(findings)} ({sum(1 for f in findings if f[0]=='ERR')} errors, {sum(1 for f in findings if f[0]=='WARN')} warnings)")
print()

if not findings:
    print("[OK] No issues found.")
else:
    by_atlas = defaultdict(list)
    for sev, atlas, msg in findings:
        by_atlas[atlas].append((sev, msg))
    for atlas in sorted(by_atlas.keys()):
        print(f"--- {atlas} ({len(by_atlas[atlas])}) ---")
        for sev, msg in by_atlas[atlas]:
            print(f"  [{sev}] {msg}")
        print()
