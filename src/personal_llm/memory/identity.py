"""Deterministic entity identity.

Root cause this module fixes: `KGNode.id` used to be `uuid4().hex` and `add_node` did
`INSERT OR REPLACE` keyed on that random id, so every mention of the same real-world
thing ("Personal LLM", say) inserted a brand new row instead of updating one. Node
identity here is instead a pure function of a normalized name (`canonical_key`) and a
type, so the same input always produces the same id - that is what makes
`upsert_entity` (memory/store.py) a real upsert and re-ingest idempotent.
"""

from __future__ import annotations

import hashlib
import re

_LEADING_ARTICLES = {"a", "an", "the"}
_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def _singularize_word(word: str) -> str:
    """Heuristic, not a lemmatizer - just the plural shapes personal notes actually
    produce. Deliberately conservative (length guards) to avoid mangling short words
    like 'is' or 'as'."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes")) and len(word) > 4:
        return word[:-2]
    # Singular words that merely end in s. "-sis" is the Greek pattern (analysis, thesis,
    # basis, diagnosis) and "-us" the Latin one (corpus, status, focus); without these,
    # "analysis" became the canonical key "analysi", which is not a word and would fail to
    # match any other spelling of the same entity. Note "-sis" rather than a blanket "-is",
    # because "APIs" must still singularize to "api".
    if word.endswith(("sis", "us")):
        return word
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def normalize_canonical_key(name: str) -> str:
    """Lowercase, strip punctuation, drop a leading article, collapse whitespace, and
    singularize simple plurals per word - so 'The Personal LLMs', 'personal llm', and
    'Personal LLM.' all resolve to the same canonical_key."""
    s = name.strip().lower()
    s = _PUNCTUATION_RE.sub(" ", s)
    s = _WHITESPACE_RE.sub(" ", s).strip()
    tokens = s.split(" ") if s else []
    if tokens and tokens[0] in _LEADING_ARTICLES:
        tokens = tokens[1:]
    tokens = [_singularize_word(t) for t in tokens]
    return " ".join(tokens)


def deterministic_entity_id(entity_type: str, canonical_key: str) -> str:
    return hashlib.sha1(f"{entity_type}|{canonical_key}".encode("utf-8")).hexdigest()


# --- entity validity -------------------------------------------------------------
#
# A local model asked for triples will happily return blank strings, the literal "null",
# a single letter, a hardware spec, or a whole descriptive clause as an "entity". None of
# those are reusable, lookup-able things, and each one that lands becomes a permanent
# node nothing ever links to again. These rules are deliberately generic (shape only, no
# per-name blocklist) so they cannot be tuned to flatter a particular corpus.

MAX_ENTITY_WORDS = 5  # a named entity is short; longer is a mis-extracted phrase or clause.
# 5 is the line because the longest genuine entity in this corpus normalizes to 5 tokens
# ("Interfaces (CLI / FastAPI / Streamlit)"), while the shortest mis-extracted clause runs 6.
_NULLISH = {"null", "none", "nan", "na", "n a", "nil", "undefined", "unknown", "true", "false"}


_UNIT_SUFFIXES = ("gb", "mb", "tb", "kb", "ghz", "mhz", "hz", "wh", "mah")
_QUANTITY_RE = re.compile(r"^\d+(\.\d+)?(" + "|".join(_UNIT_SUFFIXES) + r")$")


def is_valid_entity_name(name: str) -> bool:
    # Checked on the RAW name, before normalization strips the dashes: a command-line
    # option ("--verify", "--days") is an argument, never an entity, and the extractor
    # emits them from any chunk that quotes a shell command.
    if name.strip().startswith("-"):
        return False

    key = normalize_canonical_key(name)
    # A measured quantity ("16 GB RAM", "3.5 GHz") describes a thing rather than being
    # one. Matched by shape - a number next to or glued onto a unit - not by a list of
    # this corpus's specs. Both spacings occur, so check each token and each adjacent pair.
    tokens = key.split()
    glued = tokens + [a + b for a, b in zip(tokens, tokens[1:])]
    if any(_QUANTITY_RE.match(token) for token in glued):
        return False
    if not key or key in _NULLISH:
        return False
    if len(key) < 2:
        return False
    if not any(ch.isalpha() for ch in key):
        return False
    return len(key.split()) <= MAX_ENTITY_WORDS


def subsumes(longer: str, shorter: str) -> bool:
    """True when every token of `shorter` appears in `longer` and `longer` has strictly
    more tokens - the standard name-subsumption test ("zaid" inside "zaid ali syed").
    Applied only to people (see store.merge_subsumed_people): for projects and tools a
    longer name usually denotes a different thing ("Personal LLM" vs "Personal LLM
    Engine"), so merging there would destroy real distinctions to flatter a count."""
    long_tokens = longer.split()
    short_tokens = shorter.split()
    if not short_tokens or len(long_tokens) <= len(short_tokens):
        return False
    return set(short_tokens).issubset(set(long_tokens))


# --- entity type classification ---------------------------------------------------
#
# A pure function of the already-normalized name, not the LLM's per-mention judgment -
# on purpose. Type is part of the (type, canonical_key) identity key, so if type were
# allowed to vary between two mentions of the same entity, that variance alone would
# fragment one real-world entity across multiple node rows: exactly the bug this module
# exists to fix. Keeping classification deterministic means the same name always lands
# in the same bucket, on every run, regardless of what the LLM extracted this time.

_PERSON_NAMES = {"zaid", "zaid ali syed"}
_ORGANIZATION_KEYWORDS = ("inc", "llc", "corp", "company", "organization", "team", "university", "college")
_PLACE_KEYWORDS = ("street", "city", "country", "office", "campus")
_PROJECT_KEYWORDS = ("project", "repo", "personal llm", "ecosystem", "platform")
_TOOL_KEYWORDS = ("llm", "api", "sdk", "cli", "engine", "model", "database", "chroma", "sqlite", "app")


def classify_entity_type(canonical_key: str) -> str:
    if canonical_key in _PERSON_NAMES:
        return "person"
    if any(kw in canonical_key for kw in _ORGANIZATION_KEYWORDS):
        return "organization"
    if any(kw in canonical_key for kw in _PLACE_KEYWORDS):
        return "place"
    if any(kw in canonical_key for kw in _PROJECT_KEYWORDS):
        return "project"
    if any(kw in canonical_key for kw in _TOOL_KEYWORDS):
        return "tool"
    return "concept"


# --- relation vocabulary -----------------------------------------------------------
#
# Today's edge relations are uncontrolled free text ('is', 'is a', 'has', 'can',
# 'uses', ...). normalize_relation maps known phrasings to one of ~12 controlled
# values; anything unrecognized falls through to RELATION_FALLBACK, with the raw
# string preserved by the caller (graph/kg.py) in the edge's meta.

_RELATION_VOCAB: dict[str, tuple[str, ...]] = {
    "is_a": ("is", "is a", "is an", "was", "was a"),
    "has": ("has", "have", "has a", "owns", "own"),
    "part_of": ("part of", "belongs to", "member of"),
    "uses": ("uses", "use", "using", "used"),
    "creates": ("builds", "build", "built", "creates", "create", "created", "made", "makes", "wrote", "writes"),
    "works_on": ("works on", "working on", "developing", "develops"),
    "located_in": ("located in", "lives in", "based in"),
    "knows": ("knows", "know", "met", "meets"),
    "causes": ("causes", "cause", "leads to", "results in"),
    "precedes": ("precedes", "before", "then"),
    "mentions": ("mentions", "mention", "refers to", "about"),
}
RELATION_FALLBACK = "related"


def normalize_relation(raw: str) -> str:
    cleaned = raw.strip().lower()
    for canonical, triggers in _RELATION_VOCAB.items():
        if cleaned in triggers:
            return canonical
    return RELATION_FALLBACK
