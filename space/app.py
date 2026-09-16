"""Hugging Face Space demo for the personal-llm kernel.

Two tabs, split deliberately on what needs a key and what does not:

    Retrieve  - ingest + semantic search. Needs no key at all: embeddings are always
                local (sentence-transformers), per ADR 0002 in docs/DECISIONS/.
    Ask       - grounded generation with citations. Needs a Gemini key, because that is
                the router's real provider set (see src/personal_llm/router/providers.py) -
                Ollama has no equivalent running on a public host. The visitor pastes
                their OWN free key (https://aistudio.google.com/apikey); it is held only
                in that request's local variable, passed straight into a fresh
                GeminiProvider(api_key=...), and never touches this process's shared
                environment or gets logged - see the api_key override added to
                GeminiProvider specifically so two visitors' keys can never cross.

The corpus (space/corpus.py) is real content about the author's own projects, drawn
from career/PROFILE-FACTS.yaml, not filler - the demo is also an accurate summary.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gradio as gr

from personal_llm.memory.ingest import ingest_text
from personal_llm.memory.retrieve import semantic_search
from personal_llm.memory.store import MemoryStore
from personal_llm.memory.vectors import VectorStore
from personal_llm.rag.pipeline import ask as rag_ask
from personal_llm.router import ModelRouter
from personal_llm.router.providers import GeminiProvider, LocalEmbedder, RouterError
from corpus import CORPUS

_DATA_DIR = Path(tempfile.mkdtemp(prefix="personal-llm-space-"))
_store = MemoryStore(str(_DATA_DIR / "space.db"))
_vectors = VectorStore(str(_DATA_DIR / "space_chroma"))
# One embedder, loaded once (sentence-transformers is slow to import) and shared by every
# router below - chat_providers vary per visitor, the embedder never needs to.
_embedder = LocalEmbedder()
_ingest_router = ModelRouter(embedder=_embedder)  # no chat provider needed for ingestion

for doc in CORPUS:
    ingest_text(_store, _vectors, _ingest_router, text=doc["text"], doc_id=doc["doc_id"], source="space-demo", extract_kg=False)


def retrieve(question: str) -> str:
    if not question.strip():
        return "Type a question above - try \"What did the TCMF benchmark find?\" or \"How many tests does personal-llm have?\""
    results = semantic_search(_store, _vectors, _ingest_router, question, k=3)
    if not results:
        return "Nothing in this small demo corpus is relevant to that question."
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"**{i}. {r.doc_id}** (similarity {r.similarity:.2f})\n\n{r.text}")
    return "\n\n---\n\n".join(lines)


def answer(question: str, gemini_key: str) -> str:
    if not question.strip():
        return "Type a question above first."
    if not gemini_key.strip():
        return (
            "Paste a free Gemini key to see a grounded, cited answer (get one at "
            "https://aistudio.google.com/apikey - it costs nothing and takes about a "
            "minute). Your key is used only for this one request and is never stored "
            "or logged. Meanwhile, the Retrieve tab shows the same underlying search "
            "with no key needed at all."
        )
    ask_router = ModelRouter(chat_providers=[GeminiProvider(api_key=gemini_key.strip())], embedder=_embedder)
    try:
        result = rag_ask(_store, _vectors, ask_router, question, k=3)
    except RouterError as exc:
        return f"Gemini rejected the request: {exc}"
    if not result.grounded:
        return result.text
    sources = "\n".join(f"- {s.doc_id}: {s.snippet}" for s in result.sources)
    return f"{result.text}\n\n**Sources:**\n{sources}"


with gr.Blocks(title="Personal LLM - live demo") as demo:
    gr.Markdown(
        "# Personal LLM - live demo\n"
        "The same retrieval kernel behind [zaidwhy/personal-llm](https://github.com/zaidwhy/personal-llm) "
        "(168 offline tests, 7 eval suites, all in CI) running against a small real corpus about "
        "the author's own projects. **Retrieve** needs no key. **Ask** needs your own free Gemini key "
        "for the generation step only - retrieval and citations work identically either way."
    )
    with gr.Tab("Retrieve (no key needed)"):
        q1 = gr.Textbox(label="Question", placeholder="What did the TCMF benchmark find?")
        out1 = gr.Markdown()
        q1.submit(retrieve, inputs=q1, outputs=out1)
        gr.Button("Search").click(retrieve, inputs=q1, outputs=out1)
    with gr.Tab("Ask (bring your own free Gemini key)"):
        q2 = gr.Textbox(label="Question", placeholder="How many tests does personal-llm have?")
        key2 = gr.Textbox(label="Gemini API key", type="password", placeholder="Paste a free key from aistudio.google.com/apikey")
        out2 = gr.Markdown()
        gr.Button("Ask").click(answer, inputs=[q2, key2], outputs=out2)
    gr.Markdown(
        "---\nSource: [personal-llm on GitHub](https://github.com/zaidwhy/personal-llm) · "
        "[Zaid Ali Syed](https://zaidverse.vercel.app)"
    )

if __name__ == "__main__":
    demo.launch()
