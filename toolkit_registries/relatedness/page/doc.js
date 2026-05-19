// doc.js — shared "About this page" doc viewer.
// Adds a small floating button to every page; on click, fetches
// docs/<page>.md (relative to the page file) and renders it in a modal.
// Edit the .md sibling and refresh — no rebuild needed.
//
// Per page-doc convention:
//   page/<name>.html
//   page/docs/<name>.md     ← editable markdown sibling
//
// No external dependencies. Tiny markdown subset only (headings,
// paragraphs, lists, inline code, code blocks, links, bold/em).

(function () {
  // ---- compute current page name from URL ----
  const path = location.pathname.split("/").filter(Boolean).pop() || "";
  const pageName = path.replace(/\.html$/, "") || "index";

  // ---- inject button + modal HTML once ----
  const css = document.createElement("style");
  css.textContent = `
    .docbtn {
      position: fixed; bottom: 16px; right: 16px; z-index: 80;
      background: #2d3748; color: white; border: none; border-radius: 24px;
      padding: 9px 14px; font: 600 12.5px/1 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      cursor: pointer; box-shadow: 0 3px 12px rgba(0,0,0,0.15);
      letter-spacing: 0.02em;
    }
    .docbtn:hover { background: #1a202c; }
    .docbackdrop {
      position: fixed; inset: 0; background: rgba(0,0,0,0.4);
      opacity: 0; pointer-events: none; transition: opacity .14s ease;
      z-index: 90; display: flex; align-items: center; justify-content: center;
    }
    .docbackdrop.open { opacity: 1; pointer-events: auto; }
    .docmodal {
      max-width: 760px; width: 92%; max-height: 86vh; overflow: hidden;
      background: white; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.25);
      transform: translateY(8px); transition: transform .14s ease;
      display: flex; flex-direction: column;
    }
    .docbackdrop.open .docmodal { transform: translateY(0); }
    .docmodal .h {
      padding: 12px 18px; border-bottom: 1px solid #d8dce3;
      display: flex; align-items: center; gap: 10px;
    }
    .docmodal .h .title { flex: 1; font-weight: 600; font-size: 14px; }
    .docmodal .h .src {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px; color: #6c727f;
    }
    .docmodal .h .close {
      border: none; background: transparent; font-size: 20px; line-height: 1;
      cursor: pointer; color: #6c727f; padding: 0 4px;
    }
    .docmodal .h .close:hover { color: #b13030; }
    .docmodal .b {
      overflow-y: auto; padding: 16px 22px;
      font: 14px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #1a202c;
    }
    .docmodal .b h1 { font-size: 22px; margin: 6px 0 12px; }
    .docmodal .b h2 { font-size: 17px; margin: 18px 0 8px; }
    .docmodal .b h3 { font-size: 14px; margin: 14px 0 6px; color: #44505d; }
    .docmodal .b p  { margin: 6px 0; }
    .docmodal .b ul, .docmodal .b ol { margin: 6px 0; padding-left: 22px; }
    .docmodal .b li { margin: 3px 0; }
    .docmodal .b code {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      background: #f4f6f9; padding: 1px 5px; border-radius: 3px; font-size: 12.5px;
    }
    .docmodal .b pre {
      background: #f4f6f9; border: 1px solid #d8dce3; border-radius: 4px;
      padding: 10px 12px; overflow-x: auto;
    }
    .docmodal .b pre code { background: transparent; padding: 0; font-size: 12px; }
    .docmodal .b strong { font-weight: 600; }
    .docmodal .b a { color: #2d6cb6; text-decoration: none; }
    .docmodal .b a:hover { text-decoration: underline; }
    .docmodal .b hr { border: none; border-top: 1px solid #d8dce3; margin: 18px 0; }
    .docmodal .b .err { color: #b13030; font-style: italic; }
  `;
  document.head.appendChild(css);

  const btn = document.createElement("button");
  btn.className = "docbtn";
  btn.type = "button";
  btn.innerHTML = "📖 About this page";
  btn.title = `docs/${pageName}.md`;
  document.body.appendChild(btn);

  const backdrop = document.createElement("div");
  backdrop.className = "docbackdrop";
  backdrop.innerHTML = `
    <div class="docmodal">
      <div class="h">
        <div class="title">About this page</div>
        <div class="src">docs/${pageName}.md</div>
        <button class="close" type="button" aria-label="close">×</button>
      </div>
      <div class="b" id="__doc_body"></div>
    </div>
  `;
  document.body.appendChild(backdrop);

  // ---- minimal markdown → HTML ----
  function escapeHTML(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function inlineMD(s) {
    // inline code
    s = s.replace(/`([^`]+)`/g, (_, c) => `<code>${escapeHTML(c)}</code>`);
    // bold (**…**)
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    // italic (*…*)
    s = s.replace(/(^|[^*])\*([^*\s][^*]*?)\*/g, "$1<em>$2</em>");
    // links [text](url)
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    return s;
  }
  function renderMD(text) {
    const lines = text.split("\n");
    const out = [];
    let inCode = false, codeBuf = [];
    let inList = false, listKind = "";
    function flushList() { if (inList) { out.push(listKind === "ol" ? "</ol>" : "</ul>"); inList = false; } }
    for (let raw of lines) {
      const line = raw.replace(/\r$/, "");
      // code fences
      if (line.startsWith("```")) {
        if (!inCode) { flushList(); inCode = true; codeBuf = []; }
        else { out.push("<pre><code>" + escapeHTML(codeBuf.join("\n")) + "</code></pre>"); inCode = false; }
        continue;
      }
      if (inCode) { codeBuf.push(line); continue; }
      // headings
      let m;
      if ((m = /^# (.+)$/.exec(line))) { flushList(); out.push("<h1>" + inlineMD(escapeHTML(m[1])) + "</h1>"); continue; }
      if ((m = /^## (.+)$/.exec(line))) { flushList(); out.push("<h2>" + inlineMD(escapeHTML(m[1])) + "</h2>"); continue; }
      if ((m = /^### (.+)$/.exec(line))) { flushList(); out.push("<h3>" + inlineMD(escapeHTML(m[1])) + "</h3>"); continue; }
      // horizontal rule
      if (/^---+\s*$/.test(line)) { flushList(); out.push("<hr>"); continue; }
      // ordered list
      if ((m = /^\d+\.\s+(.+)$/.exec(line))) {
        if (!inList || listKind !== "ol") { flushList(); out.push("<ol>"); inList = true; listKind = "ol"; }
        out.push("<li>" + inlineMD(escapeHTML(m[1])) + "</li>"); continue;
      }
      // unordered list (- or *)
      if ((m = /^[-*]\s+(.+)$/.exec(line))) {
        if (!inList || listKind !== "ul") { flushList(); out.push("<ul>"); inList = true; listKind = "ul"; }
        out.push("<li>" + inlineMD(escapeHTML(m[1])) + "</li>"); continue;
      }
      // blank line
      if (!line.trim()) { flushList(); continue; }
      // paragraph
      flushList();
      out.push("<p>" + inlineMD(escapeHTML(line)) + "</p>");
    }
    flushList();
    return out.join("\n");
  }

  // ---- load + open ----
  let loaded = null;
  async function loadDoc() {
    if (loaded !== null) return loaded;
    const url = "docs/" + pageName + ".md";
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      loaded = await r.text();
    } catch (e) {
      loaded = `<no docs yet for **${pageName}** — create \`page/docs/${pageName}.md\` and edit fast.>`;
    }
    return loaded;
  }
  async function open() {
    backdrop.classList.add("open");
    const body = document.getElementById("__doc_body");
    body.innerHTML = '<p style="color: #6c727f">loading…</p>';
    const text = await loadDoc();
    body.innerHTML = renderMD(text);
  }
  function close() { backdrop.classList.remove("open"); }

  btn.addEventListener("click", open);
  backdrop.querySelector(".close").addEventListener("click", close);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
})();
