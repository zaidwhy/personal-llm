# About Personal LLM

Personal LLM is a local-first personal memory and RAG engine built by Zaid Ali Syed.
It is designed to be imported by his other projects - Recall, CivilizationOS, and his
portfolio site - instead of each project rebuilding memory, retrieval, and model
routing from scratch.

The v0.1 milestone is called the "Memory + RAG spine": ingest notes and documents,
store them as chunks and embeddings, and answer questions with cited, grounded
answers instead of hallucinating.

The engine uses a hybrid model router: local embeddings via sentence-transformers
for free, offline semantic search, and Gemini's free tier (or an optional local
Ollama model) for generating answers.
