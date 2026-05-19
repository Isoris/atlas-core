# Queue (page 11)

Lists every `action_manifest_v1` currently sitting in `02_queue/`, as produced by `lib/dispatcher.py` on `--commit`. The page never runs anything — it's a queue viewer + a *"I'll claim this one"* local annotation.

## Reads

- `../02_queue/index.json` — maintained by `lib/dispatcher.py` on every `--commit` and `--clear`. Shape: `{schema_version, queue_dir, rewritten_at, n, entries[]}`.

The browser can't list a directory, so the dispatcher writes this index file alongside the per-manifest `act_*.json` files. Page 11 fetches it on load + on Refresh.

## What you see

| | |
|---|---|
| **summary**        | totals: queued / showing / claimed (local) / queue dir / last rewritten |
| **filter bar**     | substring filters by `type` and by source `question_id` |
| **manifest card**  | one per entry: status pill + action_id + type + dataset_id + runner + submitted_at + produces (expected_outputs) |
| **dispatch row**   | "dispatched for question X via analysis Y · reason …" (from `_dispatch`) |
| **raw manifest**   | collapsible pre with the full JSON |

## Per-card buttons

- **Claim** — toggles a local-only `localStorage` flag (`atlas_queue_claims_v1`) so you can mark "I'll run this one". Doesn't write to disk.
- **Copy run command** — copies a shell hint to the clipboard (`cat <queue_dir>/<file> | jq .`).

## What to edit fast

- **Enqueue more**: `python3 -m lib.dispatcher --question <qid> [--sample-set …] --commit`
- **Empty the queue**: `python3 -m lib.dispatcher --clear --yes`
- **Re-render**: click Refresh.

## §refusals

1. **No execution.** Page 11 never runs a manifest. Use a runner (PR #3's `POST /api/actions`, biomod, a shell loop, or a human) for that.
2. **Claims are local.** Stored in `localStorage`; not visible to other browsers / other tabs of other users.
3. **No write-back to `02_queue/`.** Only the dispatcher writes there.
