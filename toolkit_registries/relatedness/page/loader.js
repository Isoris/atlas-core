// loader.js — YouTube-style top progress bar driven by fetch() activity.
//
// Wraps window.fetch in a counter. Bar shows while count > 0, fades out
// when back to 0. Stdlib JS, no per-page wiring.
//
// Exposes window.atlasLoader.start() / stop() for non-fetch async work
// that wants the bar (rare).

(function () {
  if (window.__atlasLoaderInstalled) return;
  window.__atlasLoaderInstalled = true;

  const css = document.createElement("style");
  css.textContent = `
    #atlas-loader {
      position: fixed; top: 0; left: 0; right: 0; height: 2px;
      background: transparent; z-index: 10000; pointer-events: none;
    }
    #atlas-loader > .bar {
      height: 100%; width: 0; background: linear-gradient(90deg, #2b6cb0, #4c51bf, #2f7d8d);
      box-shadow: 0 0 4px rgba(43,108,176,0.45);
      transition: width 240ms cubic-bezier(.2,.7,.3,1), opacity 200ms linear;
      opacity: 0;
    }
    #atlas-loader.active > .bar { opacity: 1; }
  `;
  document.head.appendChild(css);

  const wrap = document.createElement("div");
  wrap.id = "atlas-loader";
  wrap.innerHTML = '<div class="bar"></div>';
  // Insert on body once it exists.
  (document.body
    ? Promise.resolve(document.body)
    : new Promise(r => document.addEventListener("DOMContentLoaded", () => r(document.body)))
  ).then(b => b.appendChild(wrap));

  const bar = () => wrap.querySelector(".bar");
  let active = 0, target = 0, raf = 0;

  function tick() {
    raf = 0;
    if (active === 0) {
      bar().style.width = "100%";
      wrap.classList.remove("active");
      setTimeout(() => { bar().style.width = "0"; }, 220);
      target = 0;
      return;
    }
    wrap.classList.add("active");
    // asymptote toward 90% while requests are pending
    target = Math.min(0.9, target + (0.9 - target) * 0.15);
    bar().style.width = (target * 100).toFixed(1) + "%";
    raf = requestAnimationFrame(tick);
  }
  function start() { active++; if (!raf) raf = requestAnimationFrame(tick); }
  function stop()  { active = Math.max(0, active - 1); if (!raf) raf = requestAnimationFrame(tick); }

  window.atlasLoader = { start, stop };

  // Wrap fetch
  const origFetch = window.fetch.bind(window);
  window.fetch = function (...args) {
    start();
    return origFetch(...args).finally(stop);
  };
})();
