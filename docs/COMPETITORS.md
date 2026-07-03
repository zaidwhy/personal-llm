# Competitor / Landscape Analysis

| Product | Strength | Weakness (the gap Personal LLM targets) |
|---|---|---|
| **ChatGPT / Claude / Gemini (chat products)** | Best-in-class reasoning, huge context windows, polished UX | Stateless across sessions by default; memory features are shallow/opaque; no user-owned knowledge graph; data lives on someone else's servers |
| **Copilot** | Excellent in-editor coding assistance | Narrow scope (code only); no personal life memory |
| **Perplexity** | Strong web-grounded search + citations | No persistent personal memory; not about *you*, about the web |
| **Siri / Alexa / Google Assistant** | Ubiquitous voice, device integration | Shallow understanding, minimal memory, closed ecosystems, weak reasoning |
| **Open-source local assistants (e.g. Open Interpreter, AutoGPT-style)** | Local execution, tool use | Usually no durable structured memory system; brittle agent loops; not personalized over time |

**Personal LLM's gap to fill:** none of the above combine (a) durable, structured, user-owned memory, (b) a local-first privacy stance, (c) an engine designed to be *reused* across the owner's other projects rather than a single closed app. The moat isn't a bigger model - it's accumulated, structured, personal context that compounds over years and is portable across whatever model is best at the time (enabled by the router abstraction).

**Explicit non-goal:** competing on raw model capability. Personal LLM always calls out to best-available models (Gemini today, swappable later) rather than training its own - the value is the memory/orchestration layer around them.
