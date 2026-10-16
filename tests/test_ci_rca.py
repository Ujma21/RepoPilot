
from repopilot.ci.rca import analyze_signal, analyze_signals
from repopilot.ci.signals import FailureSignal


def make_signal(
    signal_type: str = "module_not_found",
    *,
    file: str | None = "src/app.py",
    line: int | None = 12,
    confidence: float = 0.95,
) -> FailureSignal:
    return FailureSignal(
        type=signal_type,
        message="Test failure message",
        file=file,
        line=line,
        raw_excerpt="ModuleNotFoundError: missing_module",
        confidence=confidence,
    )


def test_analyzes_missing_module():
    result = analyze_signal(make_signal())

    assert "module or package" in result.cause
    assert "ModuleNotFoundError" in result.evidence
    assert result.affected_component == "src/app.py:12"
    assert "dependency" in result.recommended_action
    assert result.confidence == 0.95


def test_handles_missing_location():
    result = analyze_signal(make_signal(file=None, line=None))

    assert result.affected_component == (
        "Not identified from the available log evidence"
    )


def test_handles_unknown_failure_type():
    result = analyze_signal(make_signal("unknown_failure"))

    assert "unclassified" in result.cause
    assert "surrounding CI logs" in result.recommended_action


def test_analyzes_multiple_signals_in_order():
    signals = [
        make_signal("module_not_found"),
        make_signal("syntax_error"),
    ]

    results = analyze_signals(signals)

    assert len(results) == 2
    assert "module or package" in results[0].cause
    assert "invalid syntax" in results[1].cause


def test_empty_signal_list():
    assert analyze_signals([]) == []
