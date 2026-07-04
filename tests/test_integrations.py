from __future__ import annotations

from personal_llm.integrations import ExternalItem, sync_external_items


def _item(source="gmail", external_id="thread-1", title="Test subject", content="Test body") -> ExternalItem:
    return ExternalItem(source=source, external_id=external_id, title=title, content=content)


def test_sync_ingests_new_items(store, vectors, router):
    result = sync_external_items(store, vectors, router, [_item()])

    assert result.ingested == 1
    assert result.skipped_existing == 0
    assert result.doc_ids == ["gmail:thread-1"]
    assert store.doc_exists("gmail:thread-1")


def test_sync_is_idempotent_on_rerun(store, vectors, router):
    items = [_item()]
    sync_external_items(store, vectors, router, items)

    result = sync_external_items(store, vectors, router, items)

    assert result.ingested == 0
    assert result.skipped_existing == 1


def test_sync_handles_mixed_new_and_existing(store, vectors, router):
    sync_external_items(store, vectors, router, [_item(external_id="thread-1")])

    result = sync_external_items(
        store, vectors, router, [_item(external_id="thread-1"), _item(external_id="thread-2")]
    )

    assert result.ingested == 1
    assert result.skipped_existing == 1
    assert result.doc_ids == ["gmail:thread-2"]


def test_sync_doc_id_includes_source():
    from personal_llm.integrations.sync import _doc_id

    gmail_item = _item(source="gmail", external_id="abc")
    drive_item = _item(source="drive", external_id="abc")

    assert _doc_id(gmail_item) == "gmail:abc"
    assert _doc_id(drive_item) == "drive:abc"
    assert _doc_id(gmail_item) != _doc_id(drive_item)


def test_sync_logs_to_audit(store, vectors, router):
    sync_external_items(store, vectors, router, [_item()])

    rows = store.recent_audit(actor="system")
    assert any(r["action"] == "external_sync" for r in rows)
