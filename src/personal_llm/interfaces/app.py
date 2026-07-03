"""Streamlit chat over the engine - shows the grounded answer plus its sources."""

from __future__ import annotations

import streamlit as st

from personal_llm.engine import build_engine
from personal_llm.memory.ingest import ingest_text
from personal_llm.rag.pipeline import ask as rag_ask
from personal_llm.router.providers import RouterError

st.set_page_config(page_title="Personal LLM", page_icon=":brain:")
st.title("Personal LLM - Your Second Brain")

engine = build_engine()

if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.header("Ingest")
    text = st.text_area("Paste text to remember", height=150)
    doc_id = st.text_input("Label (doc id)", value="pasted-note")
    if st.button("Ingest") and text.strip():
        result = ingest_text(engine.store, engine.vectors, engine.router, text=text, doc_id=doc_id, source="streamlit")
        st.success(f"Ingested {result.chunks_ingested} chunks, {result.kg_triples} KG triples.")

    st.header("Stats")
    st.json(engine.store.stats())

for role, content in st.session_state.history:
    with st.chat_message(role):
        st.write(content)

question = st.chat_input("Ask about anything you've ingested...")
if question:
    st.session_state.history.append(("user", question))
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        try:
            answer = rag_ask(engine.store, engine.vectors, engine.router, question)
        except RouterError as exc:
            st.error(str(exc))
        else:
            st.write(answer.text)
            if answer.sources:
                with st.expander("Sources"):
                    for src in answer.sources:
                        st.caption(f"{src.source}: {src.snippet}")
            st.session_state.history.append(("assistant", answer.text))
