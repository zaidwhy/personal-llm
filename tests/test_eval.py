from __future__ import annotations

from typer.testing import CliRunner

from personal_llm.eval import Assertion, EvalCase, run_eval
from personal_llm.eval.cases import builtin_cases
from personal_llm.interfaces.cli import app

runner = CliRunner()


def test_run_eval_all_pass():
    cases = [
        EvalCase("ok", run=lambda: 42, assertions=[Assertion("is 42", lambda x: x == 42)]),
    ]
    report = run_eval(cases)
    assert report.passed is True
    assert report.summary == "1/1 passed"
    assert report.results[0].failures == []


def test_run_eval_reports_failed_assertions_by_description():
    cases = [
        EvalCase(
            "bad",
            run=lambda: 1,
            assertions=[Assertion("is 2", lambda x: x == 2), Assertion("is odd", lambda x: x % 2 == 1)],
        ),
    ]
    report = run_eval(cases)
    assert report.passed is False
    assert report.results[0].failures == ["is 2"]


def test_run_eval_isolates_a_case_that_raises():
    def boom():
        raise ValueError("kaboom")

    cases = [
        EvalCase("raises", run=boom, assertions=[]),
        EvalCase("fine", run=lambda: 1, assertions=[Assertion("is 1", lambda x: x == 1)]),
    ]
    report = run_eval(cases)
    assert report.passed is False
    assert report.results[0].error == "ValueError: kaboom"
    assert report.results[1].passed is True


def test_run_eval_empty_case_list_passes_vacuously():
    report = run_eval([])
    assert report.passed is True
    assert report.summary == "0/0 passed"


def test_builtin_cases_currently_all_pass():
    # The regression baseline: today's system prompts + pipeline wiring produce
    # behavior every case expects. If this ever fails, something about ask()/
    # generate_review()'s observable behavior changed - not just their wording.
    report = run_eval(builtin_cases())
    assert report.passed, [
        (r.name, r.failures, r.error) for r in report.results if not r.passed
    ]
    assert len(report.results) == len(builtin_cases())


def test_eval_cli_command_exits_zero_and_prints_summary():
    result = runner.invoke(app, ["eval"])
    assert result.exit_code == 0
    assert "passed" in result.output
    assert "[PASS]" in result.output


def test_eval_cli_command_exits_nonzero_when_a_case_fails(monkeypatch):
    import personal_llm.interfaces.cli as cli_module

    broken_case = EvalCase("always_fails", run=lambda: 1, assertions=[Assertion("is 2", lambda x: x == 2)])
    monkeypatch.setattr(cli_module, "builtin_cases", lambda: [broken_case])

    result = runner.invoke(app, ["eval"])

    assert result.exit_code == 1
    assert "[FAIL]" in result.output
    assert "is 2" in result.output
