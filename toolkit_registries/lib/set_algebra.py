"""
toolkit_registries/lib/set_algebra.py

Materialize sample-set expressions over named groups, compute content hashes,
and answer the lookup question:

    "Do we already have a result for (analysis × sample-set × input-artifacts × params)?"

The whole point: result identity is by CONTENT, not by name. Two different
group-naming routes that produce the same member list hit the same result_id.

No I/O assumptions beyond: caller provides a `GroupResolver` that knows how to
read group definitions and a `ResultIndex` that knows how to scan
analysis_result_v1 records. Adapters for the actual atlas filesystem layout
live in each atlas's dispatcher.

Implements the contracts in:
  - sample_set_v1.schema.json
  - analysis_result_v1.schema.json
  - group_definition.schema.json

Per REGISTRY_LOOKUP.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Protocol, Sequence


SAMPLE_SET_PREFIX = "sset_"
RESULT_PREFIX = "res_"
HASH_PREFIX_LEN = 16  # hex chars taken from sha256


# --------------------------------------------------------------------------- #
# Hashing primitives                                                          #
# --------------------------------------------------------------------------- #

def canonical_members(sample_ids: Iterable[str]) -> str:
    """Canonical string form of a member list: sorted, deduplicated, '\\n'-joined,
    newline-terminated, UTF-8. The single source of truth for member-list hashing.
    """
    unique_sorted = sorted(set(sample_ids))
    return "\n".join(unique_sorted) + "\n"


def members_hash(sample_ids: Iterable[str]) -> str:
    """sha256 hex of canonical_members(...)."""
    return "sha256:" + hashlib.sha256(canonical_members(sample_ids).encode("utf-8")).hexdigest()


def sample_set_id(sample_ids: Iterable[str]) -> str:
    """sset_<first 16 hex chars of members_hash>. Matches the pattern in
    sample_set_v1.schema.json.
    """
    full = members_hash(sample_ids)[len("sha256:"):]
    return SAMPLE_SET_PREFIX + full[:HASH_PREFIX_LEN]


def canonical_params(params: Dict) -> str:
    """Canonical JSON of an analysis params dict: sorted keys, no whitespace,
    UTF-8. Strings, numbers, booleans, null, arrays, and nested dicts only.
    """
    return json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def params_hash(params: Dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_params(params).encode("utf-8")).hexdigest()


def result_id(
    analysis_id: str,
    sset_id: str,
    input_artifact_ids: Sequence[str],
    p_hash: str,
) -> str:
    """Result lookup key, derived from the four content components."""
    sorted_artifacts = ",".join(sorted(set(input_artifact_ids)))
    payload = f"{analysis_id}|{sset_id}|{sorted_artifacts}|{p_hash}".encode("utf-8")
    h = hashlib.sha256(payload).hexdigest()
    return RESULT_PREFIX + h[:HASH_PREFIX_LEN]


# --------------------------------------------------------------------------- #
# Set expressions                                                              #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SetExpr:
    """In-memory form of sample_set_v1.derived_from.

    op is one of: 'from_group', 'from_inline', 'intersect', 'union',
    'difference', 'filter'.

    parents is the list of inputs:
      - from_group:  [group_id]
      - from_inline: ignored; members are passed alongside
      - intersect / union / difference: 2+ entries, each a group_id or
        another SetExpr (recursive expressions are flattened upstream)
      - filter: [single_parent] + predicate is set
    """
    op: str
    parents: tuple = ()
    members_inline: tuple = ()
    predicate: Optional[str] = None

    @staticmethod
    def atomic(group_id: str) -> "SetExpr":
        return SetExpr(op="from_group", parents=(group_id,))

    @staticmethod
    def inline(members: Iterable[str]) -> "SetExpr":
        return SetExpr(op="from_inline", members_inline=tuple(sorted(set(members))))

    @staticmethod
    def intersect(*parents: str) -> "SetExpr":
        return SetExpr(op="intersect", parents=tuple(parents))

    @staticmethod
    def union(*parents: str) -> "SetExpr":
        return SetExpr(op="union", parents=tuple(parents))

    @staticmethod
    def difference(left: str, *minus: str) -> "SetExpr":
        return SetExpr(op="difference", parents=(left, *minus))

    @staticmethod
    def filter(parent: str, predicate: str) -> "SetExpr":
        return SetExpr(op="filter", parents=(parent,), predicate=predicate)


# --------------------------------------------------------------------------- #
# Resolution                                                                   #
# --------------------------------------------------------------------------- #

class GroupResolver(Protocol):
    """Caller-supplied: reads group_definition records or sample_set records
    and returns their materialized member list."""

    def members_of_group(self, group_id: str) -> List[str]:
        """Return the materialized sample_ids of a named group_definition.
        Used for op='from_group' parents."""
        ...

    def members_of_sample_set(self, sample_set_id: str) -> List[str]:
        """Return the materialized sample_ids of a previously-stored sample
        set. Used for nested SetExpr parents that reference sset_<hash>."""
        ...


PredicateFn = Callable[[List[str]], List[str]]


def materialize(
    expr: SetExpr,
    resolver: GroupResolver,
    predicates: Optional[Dict[str, PredicateFn]] = None,
) -> List[str]:
    """Recursively resolve a SetExpr into a sorted, deduplicated list of
    sample_ids.

    `predicates` maps predicate tags (per sample_set_v1.derived_from.predicate)
    to functions that take a member list and return a filtered list.
    """
    if expr.op == "from_inline":
        return sorted(set(expr.members_inline))

    if expr.op == "from_group":
        gid = expr.parents[0]
        return sorted(set(resolver.members_of_group(gid)))

    if expr.op in ("intersect", "union", "difference"):
        parent_sets = []
        for parent in expr.parents:
            members = _resolve_id(parent, resolver)
            parent_sets.append(set(members))
        if not parent_sets:
            return []
        if expr.op == "intersect":
            result = parent_sets[0]
            for s in parent_sets[1:]:
                result = result & s
        elif expr.op == "union":
            result = parent_sets[0]
            for s in parent_sets[1:]:
                result = result | s
        elif expr.op == "difference":
            result = parent_sets[0]
            for s in parent_sets[1:]:
                result = result - s
        return sorted(result)

    if expr.op == "filter":
        parent_members = _resolve_id(expr.parents[0], resolver)
        if predicates is None or expr.predicate not in predicates:
            raise KeyError(
                f"materialize: no predicate function registered for tag "
                f"'{expr.predicate}'. Pass it in via predicates={{tag: fn}}."
            )
        filtered = predicates[expr.predicate](parent_members)
        return sorted(set(filtered))

    raise ValueError(f"materialize: unknown op '{expr.op}'")


def _resolve_id(ident: str, resolver: GroupResolver) -> List[str]:
    """Look up an id that's either a group_id or a sample_set_id."""
    if ident.startswith(SAMPLE_SET_PREFIX):
        return resolver.members_of_sample_set(ident)
    return resolver.members_of_group(ident)


# --------------------------------------------------------------------------- #
# Result lookup                                                                #
# --------------------------------------------------------------------------- #

class ResultIndex(Protocol):
    """Caller-supplied: scans analysis_result_v1 records (or a cached index)
    and returns one by result_id, or None."""

    def get(self, result_id: str) -> Optional[Dict]:
        ...


def lookup_existing(
    analysis_id: str,
    members: Iterable[str],
    input_artifact_ids: Sequence[str],
    params: Dict,
    index: ResultIndex,
) -> Optional[Dict]:
    """Compute the result_id from content and check the index.

    Returns the analysis_result_v1 row if present, else None.
    """
    sset_id = sample_set_id(members)
    p_hash = params_hash(params)
    rid = result_id(analysis_id, sset_id, input_artifact_ids, p_hash)
    return index.get(rid)


def plan(
    analysis_id: str,
    expr: SetExpr,
    input_artifact_ids: Sequence[str],
    params: Dict,
    resolver: GroupResolver,
    index: ResultIndex,
    predicates: Optional[Dict[str, PredicateFn]] = None,
) -> Dict:
    """One-shot 'do I need to run this, or do I already have it?'

    Returns a dict:
      { status: 'cached', result: <analysis_result_v1 row> }
        when the lookup hits; caller can return the row's output_layer_id.
      { status: 'todo', result_id, sample_set_id, members, n_members,
        members_hash, params_hash, input_artifact_ids: [...sorted unique...] }
        when the lookup misses; caller assembles an action_manifest from this
        and dispatches it. The result_id is pre-computed and stable so the
        action_log_entry / output layer can carry it.
    """
    members = materialize(expr, resolver, predicates)
    sset_id = sample_set_id(members)
    m_hash = members_hash(members)
    p_hash = params_hash(params)
    sorted_artifacts = sorted(set(input_artifact_ids))
    rid = result_id(analysis_id, sset_id, sorted_artifacts, p_hash)

    hit = index.get(rid)
    if hit is not None:
        return {"status": "cached", "result": hit}
    return {
        "status": "todo",
        "result_id": rid,
        "sample_set_id": sset_id,
        "members": members,
        "n_members": len(members),
        "members_hash": m_hash,
        "params_hash": p_hash,
        "input_artifact_ids": sorted_artifacts,
    }


# --------------------------------------------------------------------------- #
# Minimal smoke tests (run: python set_algebra.py)                            #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":  # pragma: no cover
    class _InMemory:
        def __init__(self):
            self.groups = {
                "ALL": ["s1", "s2", "s3", "s4", "s5"],
                "hom_inv": ["s1", "s3", "s5"],
                "ancestry_3": ["s2", "s3", "s5"],
                "family_F1": ["s3", "s4"],
            }
            self.sets: Dict[str, List[str]] = {}
            self.results: Dict[str, Dict] = {}

        def members_of_group(self, gid):
            return self.groups[gid]

        def members_of_sample_set(self, sid):
            return self.sets[sid]

        def get(self, rid):
            return self.results.get(rid)

    mem = _InMemory()

    # Intersection of three groups
    e = SetExpr.intersect("hom_inv", "ancestry_3", "family_F1")
    members = materialize(e, mem)
    assert members == ["s3"], members
    sid = sample_set_id(members)
    print(f"intersect(hom_inv, ancestry_3, family_F1) → {members} → {sid}")

    # Hash determinism: same members, different name routes → same id
    e2 = SetExpr.inline(["s3"])
    assert sample_set_id(materialize(e2, mem)) == sid
    print("OK: different routes same members → same sample_set_id")

    # Difference
    e3 = SetExpr.difference("ALL", "family_F1")
    assert materialize(e3, mem) == ["s1", "s2", "s5"]
    print("OK: difference works")

    # plan() — miss
    plan1 = plan(
        analysis_id="ngsrelate",
        expr=e,
        input_artifact_ids=["beagle_LG28_v1", "sites_LG28_thin_v1"],
        params={"F_unknown": -1, "p": "ALL"},
        resolver=mem,
        index=mem,
    )
    assert plan1["status"] == "todo"
    print(f"OK: plan() miss → todo with result_id={plan1['result_id']}")

    # Register the result, plan again → hit
    mem.results[plan1["result_id"]] = {
        "result_id": plan1["result_id"],
        "analysis_id": "ngsrelate",
        "output_layer_id": "ngsrelate_result_demo_v1",
    }
    plan2 = plan(
        analysis_id="ngsrelate",
        expr=e,
        input_artifact_ids=["sites_LG28_thin_v1", "beagle_LG28_v1"],  # order swapped
        params={"p": "ALL", "F_unknown": -1},                          # key order swapped
        resolver=mem,
        index=mem,
    )
    assert plan2["status"] == "cached"
    print(f"OK: plan() hit → cached layer {plan2['result']['output_layer_id']}")
    print("OK: artifact order and params key order do not affect identity")
