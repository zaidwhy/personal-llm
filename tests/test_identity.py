from personal_llm.graph.kg import ExtractedTriples, Triple, extract_and_store, store_triples
from personal_llm.memory.identity import (
    classify_entity_type,
    deterministic_entity_id,
    is_valid_entity_name,
    normalize_canonical_key,
    normalize_relation,
    subsumes,
)
from personal_llm.memory.types import Chunk, KGEdge, KGNode
from personal_llm.router.schemas import Completion


def test_normalize_canonical_key_collapses_surface_variants():
    assert normalize_canonical_key("Personal LLM") == "personal llm"
    assert normalize_canonical_key("The Personal LLMs") == "personal llm"
    assert normalize_canonical_key("  personal   llm.  ") == "personal llm"
    assert normalize_canonical_key("A Cat") == "cat"
    assert normalize_canonical_key("An Apple") == "apple"


def test_normalize_canonical_key_singularizes_common_plural_shapes():
    assert normalize_canonical_key("Boxes") == "box"
    assert normalize_canonical_key("Glasses") == "glass"
    assert normalize_canonical_key("Cities") == "city"
    assert normalize_canonical_key("is") == "is"  # short word guard - not mangled


def test_normalize_canonical_key_is_idempotent():
    once = normalize_canonical_key("The Personal LLMs")
    twice = normalize_canonical_key(once)
    assert once == twice == "personal llm"


def test_deterministic_entity_id_is_pure_function_of_type_and_key():
    id_a = deterministic_entity_id("project", "personal llm")
    id_b = deterministic_entity_id("project", "personal llm")
    id_c = deterministic_entity_id("tool", "personal llm")
    assert id_a == id_b
    assert id_a != id_c


def test_classify_entity_type_is_deterministic_and_varies():
    assert classify_entity_type("zaid") == "person"
    assert classify_entity_type("personal llm") == "project"
    assert classify_entity_type("sqlite") == "tool"
    # same input, same output, every time - never a source of id drift
    assert classify_entity_type("zaid") == classify_entity_type("zaid")


def test_normalize_relation_maps_known_phrasings():
    assert normalize_relation("builds") == "creates"
    assert normalize_relation("is a") == "is_a"
    assert normalize_relation("Has") == "has"
    assert normalize_relation("uses") == "uses"


def test_normalize_relation_falls_back_for_unknown_text():
    assert normalize_relation("can") == "related"
    assert normalize_relation("something never seen before") == "related"


class _RepeatingRouter:
    """Deterministic fake chat provider - always extracts the same triple, however
    many times it is called, so idempotency can be checked without depending on a real
    LLM's run-to-run consistency."""

    def embed(self, texts):
        return [[0.0] for _ in texts]

    def complete(self, messages, schema=None):
        parsed = ExtractedTriples(
            triples=[Triple(subject="Personal LLM", relation="is", object="a project")]
        )
        return Completion(text="", parsed=parsed, provider="fake", model="fake")


def test_reingesting_the_same_corpus_twice_is_idempotent(store):
    """The single most important check from the NEXUS plan: today (uuid4 id +
    INSERT OR REPLACE) re-running extraction over the same text doubles the node/edge
    count. With deterministic (type, canonical_key) identity and upsert_entity, running
    it twice must leave the counts unchanged."""
    chunk = Chunk(doc_id="doc-1", ord=0, text="Personal LLM is a project.")
    router = _RepeatingRouter()

    extract_and_store(store, router, [chunk])
    first_pass = store.stats()

    extract_and_store(store, router, [chunk])
    second_pass = store.stats()

    assert first_pass["kg_nodes"] == second_pass["kg_nodes"]
    assert first_pass["kg_edges"] == second_pass["kg_edges"]
    assert second_pass["kg_nodes"] == 2  # "Personal LLM" and "a project", not 4
    assert second_pass["kg_edges"] == 1


def test_is_valid_entity_name_rejects_junk_extractions():
    assert not is_valid_entity_name("")
    assert not is_valid_entity_name("   ")
    assert not is_valid_entity_name("null")
    assert not is_valid_entity_name("C")  # a bare letter is not a lookup-able entity
    assert not is_valid_entity_name("2024")  # no alphabetic character
    assert not is_valid_entity_name("the graph rendered as an interactive visualization")


def test_is_valid_entity_name_accepts_real_entities():
    assert is_valid_entity_name("Personal LLM")
    assert is_valid_entity_name("Zaid Ali Syed")
    assert is_valid_entity_name("SQLite")
    assert is_valid_entity_name("MGM University")


def test_subsumes_only_when_strictly_longer_and_containing():
    assert subsumes("zaid ali syed", "zaid")
    assert not subsumes("zaid", "zaid ali syed")
    assert not subsumes("zaid", "zaid")  # identical is not subsumption
    assert not subsumes("personal llm engine", "recall")


def test_merge_subsumed_people_folds_short_name_and_keeps_edges(store):
    short = KGNode(type="person", name="Zaid")
    full = KGNode(type="person", name="Zaid Ali Syed")
    project = KGNode(type="project", name="Personal LLM")
    for node in (short, full, project):
        store.upsert_entity(node)
    store.add_edge(KGEdge(src=short.id, rel="creates", dst=project.id))

    folded = store.merge_subsumed_people()

    assert folded == 1
    people = [n for n in store.all_nodes() if n.type == "person"]
    assert [n.name for n in people] == ["Zaid Ali Syed"]
    # The edge survived the fold, repointed onto the surviving node.
    edges = store.all_edges()
    assert len(edges) == 1
    assert edges[0].src == full.id and edges[0].dst == project.id


def test_merge_subsumed_people_leaves_unrelated_names_alone(store):
    for name in ("Zaid Ali Syed", "Ada Lovelace"):
        store.upsert_entity(KGNode(type="person", name=name))

    assert store.merge_subsumed_people() == 0
    assert len({n.id for n in store.all_nodes()}) == 2


def test_merge_subsumed_people_does_not_touch_projects(store):
    """Longer project names usually denote different things, so subsumption must not
    apply there - "Personal LLM Engine" is not automatically "Personal LLM"."""
    for name in ("Personal LLM", "Personal LLM Engine"):
        store.upsert_entity(KGNode(type="project", name=name))

    assert store.merge_subsumed_people() == 0
    assert len(store.all_nodes()) == 2


def test_store_triples_drops_junk_entities(store):
    chunk = Chunk(doc_id="doc-1", ord=0, text="whatever")
    triples = [
        Triple(subject="Personal LLM", relation="uses", object="SQLite"),
        Triple(subject="null", relation="is", object="Chroma"),
        Triple(subject="Recall", relation="is", object=""),
    ]

    assert store_triples(store, chunk, triples) == 1
    assert {n.name for n in store.all_nodes()} == {"Personal LLM", "SQLite"}


def test_singular_words_ending_in_s_are_not_mangled():
    """'analysis' used to canonicalize to 'analysi' - not a word, and so unable to match
    any other spelling of the same entity. -sis and -us are singular already."""
    for word in ("analysis", "thesis", "basis", "diagnosis", "corpus", "status"):
        assert normalize_canonical_key(word) == word

    # The narrow "-sis" rule rather than a blanket "-is" one, so real plurals still fold.
    assert normalize_canonical_key("APIs") == "api"
    assert normalize_canonical_key("Agents") == "agent"


def test_command_line_flags_are_not_entities():
    """The extractor emits these from any chunk quoting a shell command. Checked on the
    raw name, because normalization strips the dashes ('--days' -> 'day')."""
    for flag in ("--verify", "--days", "--speak", "-v"):
        assert not is_valid_entity_name(flag)


def test_hardware_quantities_are_not_entities():
    for spec in ("16 GB RAM", "16GB", "3.5 GHz", "512 MB"):
        assert not is_valid_entity_name(spec)

    # Shape-matched, not blocklisted - a name that merely contains a number survives.
    assert is_valid_entity_name("Llama 3.1")
    assert is_valid_entity_name("Python 3")


def test_merge_folds_cleanly_when_the_keeper_already_has_the_same_edge(store):
    """Repointing an edge onto a keeper that already carries an identical
    (src, rel, dst) hit the UNIQUE constraint on `edges` and aborted the whole merge
    mid-fold, leaving the graph half-merged."""
    short = KGNode(type="person", name="Zaid")
    full = KGNode(type="person", name="Zaid Ali Syed")
    project = KGNode(type="project", name="Personal LLM")
    for node in (short, full, project):
        store.upsert_entity(node)
    # Both names already claim the same relationship - the collision case.
    store.add_edge(KGEdge(src=short.id, rel="creates", dst=project.id))
    store.add_edge(KGEdge(src=full.id, rel="creates", dst=project.id))

    assert store.merge_subsumed_people() == 1

    edges = store.all_edges()
    assert len(edges) == 1
    assert edges[0].src == full.id and edges[0].dst == project.id
    assert [n.name for n in store.all_nodes() if n.type == "person"] == ["Zaid Ali Syed"]
