# ADR 0002: Hybrid local+cloud model router, Gemini default, Ollama optional

**Status:** Accepted

**Context:** User wants privacy/offline capability where possible but needs strong reasoning quality and zero-cost operation today.

**Decision:** `ModelRouter` always uses a local embedding model (`sentence-transformers`) for `embed()`. For `complete()`, it health-checks a configured Ollama endpoint and uses it if reachable; otherwise falls back to Gemini free tier. Neither provider is a hard dependency - the engine degrades gracefully.

**Consequences:** Ingest/retrieve work fully offline with no API key. Generation requires either Ollama running locally or a Gemini API key. Adding a third provider (e.g. paid OpenAI) later is a new `Provider` class behind the same interface - no changes elsewhere.
