# Deploying the Space (Hugging Face)

This folder (`space/`) is the source of truth, versioned in the main repo. The live
Space is a separate git remote that only mirrors these three files
(`app.py`, `corpus.py`, `requirements.txt`, `README.md`); it does not need the rest of
this repository.

## One-time setup (Zaid, ~5 minutes - needs a Hugging Face account)

1. Create a free account at [huggingface.co](https://huggingface.co) if you don't have
   one.
2. **New Space** -> name it (e.g. `personal-llm-demo`) -> SDK: **Gradio** -> Hardware:
   **CPU basic** (free) -> Visibility: **Public**.
3. Note the Space's git URL, e.g. `https://huggingface.co/spaces/<username>/personal-llm-demo`.
4. From this repo:
   ```powershell
   git remote add space https://huggingface.co/spaces/<username>/personal-llm-demo
   git subtree push --prefix=space space main
   ```
   (`git subtree push` sends only the `space/` folder's history to the Space remote -
   the Space repo never needs the rest of this monorepo.)
5. The Space builds automatically on push (a few minutes - it installs
   `sentence-transformers` and downloads the embedding model on first build). Open the
   Space URL once the build finishes and confirm the Retrieve tab returns real results.
6. No secrets to configure - the Space needs no key of its own; each visitor supplies
   their own for the Ask tab.

## Updating the Space after a code change

```powershell
git subtree push --prefix=space space main
```

If that fails with "updates were rejected" (the Space has commits this repo doesn't,
e.g. from editing directly in the HF web UI), pull first:
```powershell
git fetch space
git subtree pull --prefix=space space main -m "Merge Space-side changes"
git subtree push --prefix=space space main
```

## Gotcha: sdk_version and websockets

`README.md`'s `sdk_version` controls which `gradio` (and therefore `gradio-client`)
version HF's Docker builder force-installs *before* it even looks at `requirements.txt`.
`gradio-client` pins a `websockets` range, and `google-genai` needs `websockets>=13.0` at
every version back to 1.0.0 (checked). Old gradio releases (`gradio-client` <1.13.2, i.e.
`sdk_version` below roughly 5.45) cap `websockets<13.0` - a hard, unresolvable conflict
with google-genai, and the build fails with `ResolutionImpossible`. `sdk_version: 6.27.0`
(what this Space uses, and what the local test below runs against) resolves to
`gradio-client==2.7.0`, which has no websockets constraint at all. If HF Spaces' default
`sdk_version` ever changes again, re-check `google-genai`'s and the new `gradio-client`'s
`websockets` ranges before assuming the pin is safe.

## Local test before pushing

```powershell
cd space
& "..\venv\Scripts\python" -m pip install -r requirements.txt
& "..\venv\Scripts\python" app.py
```
Opens at `http://127.0.0.1:7860`. Confirm both tabs work (Ask needs a real free Gemini
key to test end to end; Retrieve works immediately).
