# Conversation (page 1)

LLM-driven request resolver. **Status: deferred** — the design is locked in `toolkit_registries/LLM_FUNNEL_SPEC.md` but no LLM is wired today.

## What this page will do

Free-text research question → 5-stage funnel (decompose, pick domains, map vocabulary, refine Q&A, resolve contracts) → an ordered `action_manifest` plan that page 2 (Action) can run.

## What to edit fast

- The spec: `toolkit_registries/LLM_FUNNEL_SPEC.md`
- Controlled vocab: `toolkit_registries/vocabulary/{domains,keywords/*}.tsv`

Today, use page 2 (Action) to compose runs by hand against the existing registry.
