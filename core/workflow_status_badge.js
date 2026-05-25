// core/workflow_status_badge.js
// =====================================================================
// Topbar chip surfacing per-atlas workflow status (SPEC_workflows_v1 §5).
//
// Reads each installed atlas's workflows registry (via Registry.getWorkflows),
// fetches every workflow's status_file (SPEC §5 shape), and renders one
// compact chip showing totals across all atlases:
//
//   workflows · 🟢 2  🟡 1  🔴 0  ⚪ 1
//
// Legend: 🟢 fresh (last run succeeded + knob_hash matches)
//         🟡 stale (last run succeeded but knob_hash differs)
//         🔴 failed (last run reported stages_failed[] non-empty)
//         ⚪ never-ran (status_file 404'd)
//
// Click → popover listing each workflow with last-run timestamp + runner_id.
//
// Status_file URL resolution: relative to atlas root, so the badge fetches
// `atlases/<atlas_id>/<workflow.status_file>`. SPEC §11 says status_file
// missing == "never ran" — non-fatal, badge just classifies as ⚪.
// =====================================================================

import {
  getStatusForWorkflow,
  isWorkflowOutputStale,
  listWorkflows,
} from './workflows_registry.js';

const POLL_INTERVAL_MS = 5 * 60 * 1000;   // 5 min — workflow runs are minutes/hours, not seconds

/**
 * Mount the badge into `host`. Returns a teardown function.
 *
 * opts:
 *   - registry: Registry instance (required; the chip skips itself if absent)
 *   - manifests: Map<atlas_id, manifest> from atlas_discovery (required for the atlas root lookup)
 *   - fetch:    optional fetch override (Node tests)
 *   - poll:     optional poll interval in ms (default POLL_INTERVAL_MS)
 */
export function mountWorkflowsBadge(host, opts = {}) {
  if (!host || typeof host.appendChild !== 'function') return () => {};
  const registry = opts.registry;
  const manifests = opts.manifests;
  if (!registry || !manifests) {
    console.warn('[workflows-badge] registry + manifests required; chip will stay empty');
    return () => {};
  }

  // Build the chip skeleton up-front so layout doesn't jump when status
  // arrives. Hidden until at least one workflow exists across all atlases.
  const chip = document.createElement('span');
  chip.className = 'shell-chip workflows-badge';
  chip.style.cssText =
    'display: none; align-items: center; gap: 6px; padding: 1px 8px; ' +
    'margin: 0 4px; font: 10px ui-monospace, monospace; ' +
    'color: var(--ink-dim, #8895a8); ' +
    'border: 1px solid var(--rule, #2a3242); border-radius: 3px; cursor: pointer;';
  chip.title = 'Workflows status (click for details). ' +
               'Polled every 5 minutes from each workflow.status_file.';
  host.appendChild(chip);

  let popover = null;
  function _togglePopover() {
    if (popover && popover.parentNode) {
      popover.parentNode.removeChild(popover);
      popover = null;
      return;
    }
    popover = _buildPopover(_lastSnapshot);
    document.body.appendChild(popover);
    // Position under the chip.
    const r = chip.getBoundingClientRect();
    popover.style.top  = (r.bottom + 4) + 'px';
    popover.style.left = Math.max(8, r.right - popover.offsetWidth) + 'px';
    // Outside-click dismiss.
    const onDocClick = (ev) => {
      if (!popover) { document.removeEventListener('click', onDocClick, true); return; }
      if (popover.contains(ev.target) || chip.contains(ev.target)) return;
      _togglePopover();
      document.removeEventListener('click', onDocClick, true);
    };
    setTimeout(() => document.addEventListener('click', onDocClick, true), 0);
  }
  chip.addEventListener('click', _togglePopover);

  let _lastSnapshot = { fresh: 0, stale: 0, failed: 0, never: 0, rows: [] };
  let _pollTimer = null;

  async function _refresh() {
    const snapshot = await _collectSnapshot(registry, manifests, opts.fetch);
    _lastSnapshot = snapshot;
    if (snapshot.total === 0) {
      chip.style.display = 'none';
      return;
    }
    chip.style.display = 'inline-flex';
    chip.innerHTML =
      `<span style="color: var(--ink-dimmer, #5a6472);">workflows</span>` +
      _segment('🟢', snapshot.fresh,  'var(--good, #4ade80)') +
      _segment('🟡', snapshot.stale,  'var(--warn, #f5a524)') +
      _segment('🔴', snapshot.failed, 'var(--bad, #ef4444)') +
      _segment('⚪', snapshot.never,  'var(--ink-dim, #8895a8)');
    // Re-render the popover live if it's open.
    if (popover && popover.parentNode) {
      popover.parentNode.removeChild(popover);
      popover = _buildPopover(snapshot);
      document.body.appendChild(popover);
      const r = chip.getBoundingClientRect();
      popover.style.top  = (r.bottom + 4) + 'px';
      popover.style.left = Math.max(8, r.right - popover.offsetWidth) + 'px';
    }
  }

  // Initial fetch + poll.
  _refresh().catch(err => console.warn('[workflows-badge] initial refresh failed:', err));
  const interval = opts.poll || POLL_INTERVAL_MS;
  _pollTimer = setInterval(() => {
    _refresh().catch(err => console.warn('[workflows-badge] refresh failed:', err));
  }, interval);

  return function teardown() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    if (popover && popover.parentNode) popover.parentNode.removeChild(popover);
    if (chip.parentNode) chip.parentNode.removeChild(chip);
  };
}

function _segment(emoji, n, color) {
  if (!n) return `<span style="opacity:0.5">${emoji} 0</span>`;
  return `<span style="color: ${color}; font-weight: 600;">${emoji} ${n}</span>`;
}

// =====================================================================
// snapshot collection — pure (no DOM, no global state)
// =====================================================================

export async function _collectSnapshot(registry, manifests, fetchFn) {
  // 2026-05-21 perf: was a doubly-nested sequential `for ... await
  // getStatusForWorkflow` (per atlas × per workflow). With 7 atlases and
  // ~3 workflows each, the badge paid ~20 sequential RTTs on every poll
  // (15 s interval, first one at boot). Flatten to a list of probe
  // tasks, fan them out via Promise.all, then tally — same final shape,
  // ~20× lower wall time on cold boot.
  const tasks = [];
  for (const [atlas_id /* , manifest */] of manifests) {
    const wfReg = registry.getWorkflows && registry.getWorkflows(atlas_id);
    if (!wfReg) continue;
    const workflows = listWorkflows(wfReg);
    for (const wf of workflows) {
      const atlasRoot = `atlases/${atlas_id}`;
      tasks.push(
        getStatusForWorkflow(atlasRoot, wf,
          fetchFn ? { fetch: fetchFn } : undefined)
          .catch(() => null)
          .then(status => ({
            atlas_id,
            wf_id: wf.workflow_id,
            label: wf.label,
            status,
            kind: _classify(wf, status),
          }))
      );
    }
  }
  const rows = await Promise.all(tasks);
  let fresh = 0, stale = 0, failed = 0, never = 0;
  for (const row of rows) {
    if      (row.kind === 'fresh')  fresh  += 1;
    else if (row.kind === 'stale')  stale  += 1;
    else if (row.kind === 'failed') failed += 1;
    else                            never  += 1;
  }
  return { total: rows.length, fresh, stale, failed, never, rows };
}

function _classify(wf, status) {
  if (!status) return 'never';
  if (Array.isArray(status.stages_failed) && status.stages_failed.length > 0) return 'failed';
  if (isWorkflowOutputStale(wf, status)) return 'stale';
  return 'fresh';
}

// =====================================================================
// popover — list every workflow with its status
// =====================================================================

function _buildPopover(snapshot) {
  const pop = document.createElement('div');
  pop.className = 'workflows-badge-popover';
  pop.style.cssText =
    'position: fixed; z-index: 9999; ' +
    'background: var(--panel-2, #181d27); ' +
    'border: 1px solid var(--rule, #2a3242); ' +
    'border-radius: 4px; box-shadow: 0 8px 28px rgba(0,0,0,0.5); ' +
    'padding: 8px 0; min-width: 380px; max-width: 540px; ' +
    'font: 11px ui-monospace, monospace; color: var(--ink, #e6edf6);';
  if (!snapshot || snapshot.total === 0) {
    pop.innerHTML = '<div style="padding: 6px 14px; color: var(--ink-dim, #8895a8);">No workflows declared in any installed atlas.</div>';
    return pop;
  }
  const head = document.createElement('div');
  head.style.cssText =
    'padding: 4px 14px 8px; border-bottom: 1px solid var(--rule, #2a3242); ' +
    'color: var(--ink-dim, #8895a8); font-size: 10px;';
  head.textContent = `${snapshot.total} workflow${snapshot.total === 1 ? '' : 's'} across all atlases · 5-min poll`;
  pop.appendChild(head);
  for (const row of snapshot.rows) {
    pop.appendChild(_buildRow(row));
  }
  return pop;
}

function _buildRow(row) {
  const wrap = document.createElement('div');
  wrap.style.cssText =
    'padding: 6px 14px; display: grid; ' +
    'grid-template-columns: 16px 1fr auto; gap: 8px; align-items: center;';
  const dot = document.createElement('span');
  dot.textContent = ({ fresh: '🟢', stale: '🟡', failed: '🔴', never: '⚪' })[row.kind] || '·';
  wrap.appendChild(dot);
  const mid = document.createElement('div');
  mid.style.cssText = 'min-width: 0; overflow: hidden; text-overflow: ellipsis;';
  const name = document.createElement('div');
  name.style.cssText = 'font-weight: 600;';
  name.textContent = `${row.atlas_id} · ${row.wf_id}`;
  name.title = row.label || row.wf_id;
  mid.appendChild(name);
  const sub = document.createElement('div');
  sub.style.cssText = 'color: var(--ink-dim, #8895a8); font-size: 10px;';
  sub.textContent = _subtitle(row);
  mid.appendChild(sub);
  wrap.appendChild(mid);
  const right = document.createElement('div');
  right.style.cssText = 'color: var(--ink-dim, #8895a8); font-size: 10px; text-align: right; white-space: nowrap;';
  right.textContent = (row.status && row.status.runner_id) ? `via ${row.status.runner_id}` : '';
  wrap.appendChild(right);
  return wrap;
}

function _subtitle(row) {
  const s = row.status;
  if (!s) return 'never run · click to surface status_file path';
  if (row.kind === 'failed') {
    const failed = (s.stages_failed || []).join(', ');
    return `last run FAILED · stages: ${failed || '?'}`;
  }
  if (row.kind === 'stale') {
    return `last run succeeded · stale (knob_hash differs)`;
  }
  // fresh
  const ts = s.finished_at ? _humanizeAgo(s.finished_at) : '?';
  return `last run succeeded · ${ts}`;
}

function _humanizeAgo(iso) {
  let t;
  try { t = new Date(iso).getTime(); } catch (_) { return iso; }
  if (!isFinite(t)) return iso;
  const dt = Date.now() - t;
  if (dt < 0) return `at ${iso}`;
  const sec = Math.round(dt / 1000);
  if (sec < 60)        return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60)        return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 48)         return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}
