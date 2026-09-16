"""The sample corpus the Space demo ingests at startup.

Every fact here is drawn from career/PROFILE-FACTS.yaml (the single source of truth for
Zaid's public claims) so the demo doubles as an honest, verifiable summary of his work,
not filler text. Update this file, not the numbers in your head, when PROFILE-FACTS.yaml
changes.
"""

CORPUS = [
    {
        "doc_id": "civilizationos",
        "text": (
            "CivilizationOS is a live multi-agent society simulation: ten autonomous "
            "citizens and five AI councils behind a three-tier model router. Its "
            "retrieval method, TCMF, fuses episodic memory with proximity over a "
            "causal knowledge graph. The first, multiplicative version of TCMF scored "
            "recall at 5 of 0.02 on the causal signal it was built to exploit, where "
            "that signal alone reaches 1.00; the corrected additive version recovered "
            "it, benchmarked against six baselines over three hundred scenarios. "
            "It runs live at civilization-os-murex.vercel.app, with 76 API tests and "
            "152 benchmark tests in continuous integration."
        ),
    },
    {
        "doc_id": "personal-llm",
        "text": (
            "Personal LLM is a local-first memory and retrieval-augmented-generation "
            "kernel: ingest notes, retrieve them ranked by similarity, importance, and "
            "recency, and answer questions grounded in citations, refusing honestly "
            "when nothing in memory supports an answer. It has 168 offline tests and "
            "is imported as a shared kernel by two other projects, second-brain and "
            "github-pr-agent, bringing the total to 334 tests across the three. This "
            "demo is running that exact kernel."
        ),
    },
    {
        "doc_id": "cold-read",
        "text": (
            "COLD READ is a research study measuring how many words a person writes "
            "before a local language model can infer who they are. The finding is "
            "that the threshold belongs to the reading model, not the text: one model "
            "needed fifty words to beat chance at guessing gender, another needed "
            "eight hundred words on identical writing. Star sign served as a negative "
            "control and never left chance in either model, and one finding from the "
            "first model failed to replicate on the second and is reported as such. "
            "It is archived with a permanent DOI, 10.5281/zenodo.22309660."
        ),
    },
    {
        "doc_id": "augur",
        "text": (
            "AUGUR measured where time-locked language models actually believe they "
            "stand in history. A model trained only on text published before 1938 "
            "answers the question what year is it with 1899, four to eight decades "
            "before its stated cutoff. Two model families were tested across "
            "fourteen probes at temperature zero, and whether a date anchor could "
            "move the model turned out to be a second, independent axis: one model "
            "jumped forty years, the other refused. It is archived with a permanent "
            "DOI, 10.5281/zenodo.22309658."
        ),
    },
    {
        "doc_id": "zabira-academy",
        "text": (
            "As founding software engineer intern at Zabira Academy, a live learning "
            "platform taking real payments, an independent audit found twenty four "
            "security and quality issues, one critical, and the fixes shipped across "
            "twenty seven merged pull requests reviewed by the platform's owner. One "
            "incident, a broken password reset, was root caused end to end over SSH "
            "through a missed migration, a disabled exec call, a database account "
            "lockout, and a MySQL eight PDO authentication plugin mismatch."
        ),
    },
    {
        "doc_id": "open-source",
        "text": (
            "Three pull requests are merged into open source Python libraries "
            "totalling roughly thirteen thousand four hundred stars: jd slash "
            "tenacity pull request six hundred sixty eight fixed static typing for "
            "retry decorated instance methods, dry python slash returns pull request "
            "two thousand four hundred eighty relaxed a parameter type from "
            "Coroutine to the broader Awaitable protocol, and memgraph slash "
            "gqlalchemy pull request three hundred ninety added an is not null "
            "operator to its query builder."
        ),
    },
]
