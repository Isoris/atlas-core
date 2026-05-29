// filters.js — small UX helpers shared across pages
//
// 1. attachClearButton(input)
//    Wraps a text input in a relative container, adds a floating "✕"
//    that appears only when the input has a value. Click clears,
//    dispatches an `input` event so re-render fires, and refocuses
//    the field. Pressing Escape while focused does the same.
//
// 2. data-clear="true"
//    Any <input data-clear="true"> picks up the behaviour
//    automatically on DOMContentLoaded — no per-page wiring needed.
//
// 3. autoAttachAll()
//    Idempotent; safe to re-run after the page re-renders.
//
// Pure stdlib JS, no framework, no dependencies.

(function () {
  if (window.__atlasFiltersInstalled) return;
  window.__atlasFiltersInstalled = true;

  const css = document.createElement("style");
  css.textContent = `
    .atlasfilter-wrap {
      position: relative; display: inline-block; vertical-align: middle;
    }
    .atlasfilter-wrap > input { padding-right: 26px !important; }
    .atlasfilter-clear {
      position: absolute; right: 5px; top: 50%; transform: translateY(-50%);
      width: 18px; height: 18px; border-radius: 3px;
      border: 1px solid transparent; background: transparent;
      color: #6c727f; font-size: 13px; line-height: 14px; text-align: center;
      cursor: pointer; padding: 0; user-select: none;
      opacity: 0; pointer-events: none; transition: opacity 80ms linear;
    }
    .atlasfilter-wrap.has-value .atlasfilter-clear {
      opacity: 1; pointer-events: auto;
    }
    .atlasfilter-clear:hover { color: #fff; background: #c53030; border-color: #c53030; }
  `;
  document.head.appendChild(css);

  function attachClearButton(input) {
    if (!input || input.__atlasFilterWired) return;
    input.__atlasFilterWired = true;

    // Wrap the input so the absolute-positioned ✕ has an anchor.
    const wrap = document.createElement("span");
    wrap.className = "atlasfilter-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "atlasfilter-clear";
    btn.title = "Clear (Esc)";
    btn.setAttribute("aria-label", "Clear filter");
    btn.textContent = "✕";
    wrap.appendChild(btn);

    function syncVisibility() {
      wrap.classList.toggle("has-value", (input.value || "").length > 0);
    }
    function doClear() {
      if (!input.value) return;
      input.value = "";
      // Fire `input` so the page's existing oninput / addEventListener fires.
      input.dispatchEvent(new Event("input", { bubbles: true }));
      // …and `change`, for code listening to that.
      input.dispatchEvent(new Event("change", { bubbles: true }));
      syncVisibility();
      input.focus();
    }

    input.addEventListener("input", syncVisibility);
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && input.value) {
        ev.preventDefault();
        ev.stopPropagation();   // don't let it bubble into search.js / doc.js Esc handlers
        doClear();
      }
    });
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      doClear();
    });
    syncVisibility();
  }
  window.attachClearButton = attachClearButton;

  function autoAttachAll(root) {
    (root || document).querySelectorAll('input[data-clear="true"]').forEach(attachClearButton);
  }
  window.attachAllClearButtons = autoAttachAll;

  // window.clearFilter(inputId) — programmatic clear, used by inline
  // "Clear filter" links inside empty-state messages.
  window.clearFilter = function (inputId) {
    const inp = document.getElementById(inputId);
    if (!inp) return;
    inp.value = "";
    inp.dispatchEvent(new Event("input", { bubbles: true }));
    inp.dispatchEvent(new Event("change", { bubbles: true }));
    inp.focus();
  };

  // window.emptyStateHtml(inputId, message?) — canonical empty-state
  // markup with an inline "✕ Clear filter" link.
  window.emptyStateHtml = function (inputId, message) {
    const msg = message || "No results match the current filter.";
    return `<div class="empty" style="padding:18px;color:#6c727f;text-align:center">
      ${msg}
      <a href="javascript:void(0)" onclick="window.clearFilter('${inputId}')"
         style="display:inline-block;margin-left:8px;color:#2b6cb0;text-decoration:none;
                border:1px solid #cfe2f7;border-radius:3px;padding:1px 7px;font-size:11.5px">
        ✕ Clear filter
      </a>
    </div>`;
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => autoAttachAll());
  } else {
    autoAttachAll();
  }
})();
