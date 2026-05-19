# Conversation (page 1)

Type a research question → token-by-token matches surface every registered **product / question / atlas / estimand** ranked by relevance. No LLM, no remote calls.

## How it works

1. The input text is tokenised: lowercase, strip punctuation, length ≥ 3, drop common stop-words.
2. Each registered item is scored by how many tokens appear in its `id` / `label` / `description` / `tags` / `valid_for`.
3. Field weights: `id` 4, `label` 3, `tags` / `valid_for` 2, `description` 1.
4. Each match shows the matched tokens + a click-through to its detail page (page 8 for questions / products / estimands, page 10 for atlases) via the `?focus=…` deep-link from PR #20.

## Reads

- `01_registry/products.jsonl`
- `01_registry/questions.jsonl`
- `01_registry/atlases.jsonl`
- `01_registry/estimands.jsonl`

## What to edit fast

- Add a row to `products.jsonl` / `questions.jsonl` with a meaningful `label` + `description` + `tags` / `valid_for` — the matcher picks it up automatically.
- Stop-words / scoring weights: edit the `STOP` set and the field weights in the page's inline `<script>`.

## What this page is NOT (yet)

This is **Phase B** of the LLM funnel spec (`toolkit_registries/LLM_FUNNEL_SPEC.md`) — the deterministic vocabulary-mapping stage. The fuller funnel (Stage A: extract intent → Stage C: propose graph) needs an LLM provider; it'll land later and feed its output into the same matching panes below.

## §refusals

1. **No LLM, no API call.** Pure client-side text search over the JSONLs.
2. **No write-back.** Asking a question doesn't mutate the registry.
3. **Bridges to page 8.** Every match is a `?focus=` deep link — the Manager is what tells you whether the matched item is ready.
