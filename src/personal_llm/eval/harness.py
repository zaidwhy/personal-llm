"""Prompt-regression eval harness (docs/ROADMAP.md v0.3 "richer router" groundwork).

A system prompt (rag/pipeline.py's `_SYSTEM`, review/weekly.py's `_SYSTEM`, ...) can be
reworded for a genuinely good reason - tighter instructions, a new constraint - and
still silently break the *behavior* callers depend on: grounding falling back to
"I don't have anything in memory" when it shouldn't, a review report losing a field,
citations disappearing. Nothing in the existing test suite is organized to catch that
class of regression as a single pass/fail sweep; this harness is.

An `EvalCase` pairs a `run` callable (usually: build fakes, call a pipeline function,
return its output) with `Assertion`s that check the *shape and content* of that output,
never its literal prompt wording - so a prompt is free to change as long as behavior
holds. Everything here is pure/offline: no network, no API key, same bar as the rest of
the suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Assertion:
    """One named check over a case's output. `check` returns True (pass) or False (fail)."""

    description: str
    check: Callable[[Any], bool]


@dataclass(frozen=True)
class EvalCase:
    """One eval case: `run()` produces an output, then every assertion is checked against it."""

    name: str
    run: Callable[[], Any]
    assertions: list[Assertion]


@dataclass(frozen=True)
class CaseResult:
    name: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class EvalReport:
    results: list[CaseResult]

    @property
    def passed(self) -> bool:
        """True only if every case passed (and none raised)."""
        return all(r.passed for r in self.results)

    @property
    def summary(self) -> str:
        """One-line pass/fail count, e.g. "3/4 passed"."""
        passed_count = sum(1 for r in self.results if r.passed)
        return f"{passed_count}/{len(self.results)} passed"


def run_eval(cases: list[EvalCase]) -> EvalReport:
    """Run every case and collect a report. A case whose `run()` raises is recorded as a
    failure with the exception message rather than propagating, so one broken case
    never hides the results of the rest.
    """
    results = []
    for case in cases:
        try:
            output = case.run()
        except Exception as exc:  # noqa: BLE001 - deliberately broad: isolate one bad case
            results.append(CaseResult(case.name, passed=False, error=f"{type(exc).__name__}: {exc}"))
            continue
        failures = [a.description for a in case.assertions if not a.check(output)]
        results.append(CaseResult(case.name, passed=not failures, failures=failures))
    return EvalReport(results)
