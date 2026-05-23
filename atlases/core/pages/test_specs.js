// Smoke tests for the SPECs page's pure helpers.
//
// Mirrors test_inventory.js — pure-function coverage only; mount() is
// DOM-coupled and tested in-browser at #/core/specs.
//
// Run from atlas-core root:
//   node atlases/core/pages/test_specs.js
//
// Covers:
//   - esc            — HTML escaping for &, <, >, ", '; null / undefined yield ''
//   - renderMarkdown — headings, paragraphs, fenced code, inline code,
//                      bullet + numbered lists, links, bold/italic,
//                      GFM tables, blockquotes, horizontal rules,
//                      HTML-in-source escaped, mixed structures

import { esc, renderMarkdown } from './specs.js';

let _failed = 0;
let _passed = 0;

function eq(a, b, msg) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    console.error(`FAIL: ${msg}\n  expected: ${JSON.stringify(b)}\n  got:      ${JSON.stringify(a)}`);
    _failed++;
    return;
  }
  _passed++;
  console.log(`  ok: ${msg}`);
}

function contains(html, marker, msg) {
  if (typeof html !== 'string' || !html.includes(marker)) {
    console.error(`FAIL: ${msg}\n  marker not in output: ${marker}\n  got: ${html}`);
    _failed++;
    return;
  }
  _passed++;
  console.log(`  ok: ${msg}`);
}

function lacks(html, marker, msg) {
  if (typeof html === 'string' && html.includes(marker)) {
    console.error(`FAIL: ${msg}\n  unexpected marker in output: ${marker}\n  got: ${html}`);
    _failed++;
    return;
  }
  _passed++;
  console.log(`  ok: ${msg}`);
}

// ====== esc =============================================================

console.log('esc:');
{
  eq(esc('hello'), 'hello', 'plain text unchanged');
  eq(esc('<script>'), '&lt;script&gt;', 'tags escaped');
  eq(esc('a & b'), 'a &amp; b', 'ampersand escaped');
  eq(esc('"quoted"'), '&quot;quoted&quot;', 'double-quote escaped');
  eq(esc("it's"), 'it&#39;s', 'single-quote escaped');
  eq(esc(null), '', 'null → empty string');
  eq(esc(undefined), '', 'undefined → empty string');
  eq(esc(0), '0', 'number 0 → "0" (not empty)');
}

// ====== renderMarkdown: headings =======================================

console.log('\nrenderMarkdown — headings:');
{
  contains(renderMarkdown('# Top'),     '<h1 class="spc-md-h spc-md-h1">Top</h1>', 'H1');
  contains(renderMarkdown('## Two'),    '<h2 class="spc-md-h spc-md-h2">Two</h2>', 'H2');
  contains(renderMarkdown('### Three'), '<h3 class="spc-md-h spc-md-h3">Three</h3>', 'H3');
  contains(renderMarkdown('###### Six'), '<h6 class="spc-md-h spc-md-h6">Six</h6>', 'H6');
  lacks(renderMarkdown('####### Seven'), '<h7', 'no H7 (max is H6)');
}

// ====== renderMarkdown: paragraphs + inline =============================

console.log('\nrenderMarkdown — paragraphs + inline:');
{
  const html = renderMarkdown('Hello world.');
  contains(html, '<p class="spc-md-p">Hello world.</p>', 'simple paragraph');
}
{
  // Two consecutive non-blank lines merge into one paragraph (with space).
  const html = renderMarkdown('line one\nline two');
  contains(html, 'line one line two', 'consecutive lines join with space');
}
{
  // Blank line separates paragraphs.
  const html = renderMarkdown('para 1\n\npara 2');
  const matches = html.match(/<p class="spc-md-p">/g) || [];
  if (matches.length === 2) {
    console.log('  ok: blank line separates paragraphs');
    _passed++;
  } else {
    console.error(`FAIL: expected 2 paragraphs, got ${matches.length}`);
    _failed++;
  }
}
{
  contains(renderMarkdown('**bold**'), '<strong>bold</strong>',     'bold (**)');
  contains(renderMarkdown('__bold__'), '<strong>bold</strong>',     'bold (__)');
  contains(renderMarkdown('an *em* word'),    '<em>em</em>',        'italic (*)');
  contains(renderMarkdown('an _em_ word'),    '<em>em</em>',        'italic (_)');
}
{
  contains(renderMarkdown('use `foo()` here'), '<code class="spc-md-icode">foo()</code>', 'inline code');
}
{
  // Inline code preserves HTML inside.
  const html = renderMarkdown('try `<div>` tag');
  contains(html, '<code class="spc-md-icode">&lt;div&gt;</code>', 'inline code escapes HTML');
}
{
  // Link.
  contains(renderMarkdown('[atlas](https://example.com)'),
           '<a href="https://example.com"', 'link href');
  contains(renderMarkdown('[atlas](https://example.com)'),
           '>atlas</a>', 'link text');
}
{
  // HTML in source must be escaped.
  const html = renderMarkdown('beware <script>alert(1)</script>');
  contains(html, '&lt;script&gt;alert(1)&lt;/script&gt;', 'inline HTML escaped');
  lacks(html, '<script>', 'no raw <script>');
}

// ====== renderMarkdown: code blocks =====================================

console.log('\nrenderMarkdown — code blocks:');
{
  const html = renderMarkdown('```\nplain code\n```');
  contains(html, '<pre class="spc-md-pre">', 'fenced code wrapper');
  contains(html, '>plain code</code>', 'fenced code body preserved');
}
{
  const html = renderMarkdown('```python\nx = 1\n```');
  contains(html, 'class="lang-python"', 'fenced code with language class');
}
{
  // HTML in code must be escaped, NOT interpreted.
  const html = renderMarkdown('```\n<b>x</b>\n```');
  contains(html, '&lt;b&gt;x&lt;/b&gt;', 'code-block HTML escaped');
  lacks(html, '<b>x</b>',                'no raw <b> in output');
}
{
  // Multi-line code block.
  const html = renderMarkdown('```\nline 1\nline 2\nline 3\n```');
  contains(html, 'line 1\nline 2\nline 3', 'multi-line code preserved');
}

// ====== renderMarkdown: lists ===========================================

console.log('\nrenderMarkdown — lists:');
{
  const html = renderMarkdown('- one\n- two\n- three');
  contains(html, '<ul class="spc-md-ul">', 'bullet list opener');
  contains(html, '<li>one</li>',  'first item');
  contains(html, '<li>three</li>', 'third item');
}
{
  // Numbered list.
  const html = renderMarkdown('1. alpha\n2. beta\n3. gamma');
  contains(html, '<ol class="spc-md-ol">', 'ordered list opener');
  contains(html, '<li>alpha</li>',  'first numbered item');
}
{
  // Star bullets (alternate syntax).
  const html = renderMarkdown('* a\n* b');
  contains(html, '<ul class="spc-md-ul">', 'star-bullet list');
  contains(html, '<li>a</li>',             'star-bullet item');
}

// ====== renderMarkdown: tables ==========================================

console.log('\nrenderMarkdown — tables:');
{
  const md = '| col1 | col2 |\n|------|------|\n| a | b |\n| c | d |';
  const html = renderMarkdown(md);
  contains(html, '<table class="spc-md-tbl">', 'table wrapper');
  contains(html, '<th>col1</th>',              'first header cell');
  contains(html, '<th>col2</th>',              'second header cell');
  contains(html, '<td>a</td>',                 'first data cell');
  contains(html, '<td>d</td>',                 'last data cell');
}
{
  // Table with inline code in a cell.
  const md = '| name | val |\n|---|---|\n| `x` | 1 |';
  const html = renderMarkdown(md);
  contains(html, '<code class="spc-md-icode">x</code>', 'inline code inside table cell');
}

// ====== renderMarkdown: misc structure ==================================

console.log('\nrenderMarkdown — misc:');
{
  contains(renderMarkdown('---'),      '<hr class="spc-md-hr">', 'horizontal rule (---)');
  contains(renderMarkdown('***'),      '<hr class="spc-md-hr">', 'horizontal rule (***)');
}
{
  contains(renderMarkdown('> quoted'), '<blockquote class="spc-md-bq">quoted</blockquote>', 'blockquote');
}
{
  // Heading followed immediately by paragraph (no blank line).
  const html = renderMarkdown('## Section\npara text');
  contains(html, '<h2 class="spc-md-h spc-md-h2">Section</h2>', 'heading first');
  contains(html, '<p class="spc-md-p">para text</p>',            'paragraph after heading');
}
{
  // Empty input.
  eq(renderMarkdown(''), '', 'empty input → empty output');
}
{
  // CRLF line endings (Windows-edited SPEC files).
  const html = renderMarkdown('# Title\r\n\r\nbody.');
  contains(html, '<h1 class="spc-md-h spc-md-h1">Title</h1>', 'CRLF heading');
  contains(html, '<p class="spc-md-p">body.</p>',              'CRLF paragraph');
}

// ====== summary =========================================================

console.log();
if (_failed > 0) {
  console.error(`FAILED: ${_failed} of ${_passed + _failed} assertions failed`);
  process.exit(1);
}
console.log(`ALL OK (${_passed} assertions)`);
