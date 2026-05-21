# ADR 007 — BYOK LLM + embedding abstraction with local-Ollama default

**Status:** Accepted (2026-05-21)
**Author:** Shaurya

## Context

Every Suture module past the foundation needs an LLM (classification, extraction, eval, voice, appeal generation) and most need embeddings (RAG over payer rules, semantic search). Two pressures shape this:

1. **Cost and key management.** v1 ships solo. The only paid service we want is Anthropic, and even that should be opt-in. CI must run free — no API key in the test environment. Local-only dev must work on a laptop without internet.
2. **Vendor lock-in.** If each module hard-imports `anthropic` or `openai` directly, switching providers (or running benchmarks across providers) is a rewrite. The abstraction needs to be in place *before* Module 2 so it's never a retrofit.

Plus a cost-safety gap: `seeds/scripts/_claude.py` (the synthetic-data wrapper) currently makes a live Anthropic call on any cache miss if `ANTHROPIC_API_KEY` is set in env. Easy to leave a key in `.env` and accidentally burn credits when prompts change.

Three options:

1. **Direct SDK imports per module.** Simplest today, painful tomorrow.
2. **Abstraction + cloud-only default (Anthropic).** Clean interface but ties CI to a paid key.
3. **Abstraction + local-default (Ollama), BYOK opt-in for cloud.** More setup, but zero-cost CI, PHI never leaves the box for local dev, and the abstraction lets us flip providers per-env.

## Decision

Option 3.

- **`LLMProvider` ABC** in `apps/api/app/services/llm/base.py` with abstract `async generate(...)` and a concrete `async extract_json(...)` that handles markdown-fence stripping, `<think>...</think>` block stripping, and JSON parsing in one place.
- **Three concrete providers:** `OllamaProvider` (default, no SDK dep — just `httpx`), `OpenAIProvider` and `AnthropicProvider` (both lazy-import their SDK inside `__init__` and raise a clear `ImportError("pip install ...")` if missing).
- **`get_llm_provider()` factory** in `app/services/llm/factory.py`, decorated with `@functools.lru_cache(maxsize=1)`, driven by the `LLM_PROVIDER` env var (defaults to `"ollama"`). OpenAI/Anthropic arms check for their respective API key env vars and raise `ValueError` if missing.
- **`EmbeddingProvider` ABC** with a symmetric shape in `app/services/embedding/`. Only `OllamaEmbeddingProvider` ships in this PR (model `bge-m3`, 1024-dim, hybrid dense+sparse, 8K context).
- **Schema:** `payer_rules.embedding` migrated from `vector(384)` (sized for the old `all-MiniLM-L6-v2` plan) to `vector(1024)` (bge-m3) via Alembic migration 0003. Column is currently unpopulated, so the migration is a single `ALTER TABLE ... USING NULL`. No ivfflat index yet — deferred to Module 4 when RAG actually queries.
- **`seeds/scripts/_claude.py` hardening:** new `allow_live_api: bool = False` constructor param plus `SUTURE_ALLOW_LIVE_LLM=1` env override. On cache miss with both off, raises `CacheMissNotAllowed` and refuses the call — even if `ANTHROPIC_API_KEY` is set (with a one-shot warning log explaining the refusal). Default behavior is cache-only; live calls require explicit opt-in.

Local models chosen, with evidence:

- **MedGemma 1.5 4B** (extraction). Local benchmark on a synthetic discharge summary produced clean JSON wrapped only in a ` ```json ... ``` ` fence — a single regex strip away from `json.loads`. Fast enough for interactive use on a dev laptop.
- **Qwen 3 8B** (comparison baseline). Higher capability ceiling, but leaks `<think>...</think>` reasoning even with the `/no_think` control token in some cases. Hence the belt-and-suspenders in `OllamaProvider`: prepend `/no_think` to the prompt for Qwen models *and* regex-strip any thinking blocks from the response.
- **bge-m3** (embeddings). 1024-dim, hybrid dense+sparse retrieval, 8K context window. Runs on Ollama, no API key.

## Consequences

### Positive
- Zero-cost CI. The full test suite runs without any paid API key.
- PHI never has to leave the box for local dev — Ollama is loopback.
- Module 2+ code is provider-agnostic. Swapping providers is one env var.
- `payer_rules.embedding` dimension agrees with the actual model before any data exists — no retrofit migration later.
- Accidental live API calls during seed regeneration are now impossible without explicit `SUTURE_ALLOW_LIVE_LLM=1`.
- Eval harness can route the same prompt through multiple providers for head-to-head comparison.

### Negative
- Local Ollama is slower and lower-quality than Sonnet for hard extraction. Modules that need top-tier quality will pin `LLM_PROVIDER=anthropic` per-env.
- `lru_cache` on the factory means tests that twiddle `LLM_PROVIDER` between cases must reset it — handled via an autouse `_reset_provider_cache` fixture, but it's one more thing to remember.
- Lazy SDK imports surface "missing package" errors at provider construction time rather than module import. Slightly less obvious in a stack trace, but the error message is explicit (`pip install openai to use OpenAIProvider`).
- Two Anthropic codepaths now exist: `AnthropicProvider` (async, used by app code, opt-in) and `FixtureBackedClaude` in `seeds/scripts/_claude.py` (sync, Haiku, fixture-cached, cost-capped). Distinct purposes; consolidation deferred unless it becomes painful.

### Rejected: hard SDK dependencies in pyproject
Adding `openai` and `anthropic` as main deps inflates the install for the 95% of users running Ollama. Lazy imports inside provider `__init__` give the same ergonomics with zero default bloat.

### Rejected: no abstraction; direct `import anthropic` per module
Locks v1 to Anthropic. Breaks the free-CI story. Forces a future refactor across every module that touched the SDK.

### Rejected: cloud-first default with Anthropic Sonnet
Cleanest interface but every contributor needs a paid key to run tests, and PHI leaves the box for every local dev experiment. Wrong defaults for a HIPAA-class product in v1.

### Rejected: enum + match instead of ABC
Works, but `LLMProvider(ABC)` enforces method signatures at type-check time and is mypy-strict-friendly. ABCs are also the idiomatic Python pattern for this shape.

## Production path (deferred to paid deploy)

1. Set `LLM_PROVIDER=anthropic` per-env for quality-critical paths (extraction, prior-auth reasoning). Ollama can stay for cheaper paths (eval, classification).
2. Wrap `get_llm_provider().generate(...)` in a logging decorator that writes to `ai_invocations` — Module 2 work, table already exists.
3. Add `Vertex` / `Bedrock` providers when an enterprise customer asks. The ABC absorbs them with no caller changes.
4. Consolidate `seeds/scripts/_claude.py` into the same abstraction once the cost-cap + fixture-cache pattern is generalized.

## Revisit when

- Module 4 RAG lands — decide ivfflat vs. HNSW index based on observed query patterns.
- First paying customer — likely flip default to Anthropic Sonnet.
- A benchmark shows MedGemma 1.5 4B is unfit for extraction — re-pick the local default (next candidates: Qwen 3 with stricter thinking suppression, or a newer Gemma).
- `openai` / `anthropic` SDKs become required by more than one module — re-evaluate whether they should be main deps.
