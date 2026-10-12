
from repopilot.ci.parser import parse_log


def test_detects_missing_python_module():
    signals = parse_log(
        'ModuleNotFoundError: No module named "requests"'
    )

    assert len(signals) == 1
    assert signals[0].type == "module_not_found"
    assert "requests" in signals[0].message
    assert signals[0].confidence >= 0.9


def test_detects_missing_npm_script():
    signals = parse_log("npm ERR! Missing script: 'build'")

    assert len(signals) == 1
    assert signals[0].type == "npm_missing_script"
    assert "build" in signals[0].message


def test_detects_syntax_error_and_location():
    log = (
        '  File "src/app.py", line 42\n'
        "    invalid syntax here\n"
        "SyntaxError: invalid syntax"
    )

    signals = parse_log(log)
    syntax = next(s for s in signals if s.type == "syntax_error")

    assert syntax.file == "src/app.py"
    assert syntax.line == 42


def test_detects_common_failure_signatures():
    log = "\n".join([
        "OOMKilled",
        "FAILED tests/test_example.py::test_value",
        "error: pathspec 'missing.txt' did not match any file",
        "Permission denied",
        "FileNotFoundError: config.yml",
    ])

    types = {signal.type for signal in parse_log(log)}

    assert "out_of_memory" in types
    assert "test_failure" in types
    assert "git_pathspec" in types
    assert "permission_denied" in types
    assert "file_not_found" in types


def test_empty_log_returns_no_signals():
    assert parse_log("") == []
    assert parse_log("  \n ") == []


def test_unrecognized_log_returns_no_signals():
    assert parse_log("Build started\nBuild completed successfully") == []


def test_signal_count_is_bounded():
    log = "\n".join(
        "Permission denied" for _ in range(150)
    )

    assert len(parse_log(log)) <= 100


def test_log_size_is_bounded():
    log = "ordinary output\n" * 600_000

    signals = parse_log(log)
    assert signals == []
