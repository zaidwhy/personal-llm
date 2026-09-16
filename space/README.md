---
title: Personal LLM Demo
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 5.0.0
app_file: app.py
pinned: false
license: mit
---

# Personal LLM - live demo

The retrieval kernel behind [zaidwhy/personal-llm](https://github.com/zaidwhy/personal-llm)
(168 offline tests, 7 eval suites, all in CI), running against a small real corpus about
the author's own projects.

- **Retrieve** tab: semantic search with citations. No API key needed - embeddings are
  always local (sentence-transformers).
- **Ask** tab: grounded generation with citations. Paste your own free Gemini key
  ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) - it is used only
  for that one request and never stored or logged.

Source for this Space: [`space/`](https://github.com/zaidwhy/personal-llm/tree/main/space)
in the main repository. See [`space/DEPLOYMENT.md`](https://github.com/zaidwhy/personal-llm/blob/main/space/DEPLOYMENT.md)
for how this Space is kept in sync with that source.
