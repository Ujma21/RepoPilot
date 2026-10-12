
import json

from repopilot.core.tracing import Tracer


def test_tracer_records_events_and_summary():
    tracer = Tracer()

    tracer.record_llm_call("test-model", 120.5)
    tracer.record_tool_call("git_status", {})
    tracer.record_tool_result(
        "git_status",
        {"success": True, "status": "## master"},
        20.0,
    )

    summary = tracer.summary()

    assert summary["total_llm_calls"] == 1
    assert summary["total_tool_calls"] == 1
    assert summary["total_tool_results"] == 1
    assert summary["total_errors"] == 0
    assert summary["total_steps"] == 3


def test_tracer_records_errors():
    tracer = Tracer()
    tracer.record_error("Provider unavailable")

    assert tracer.summary()["total_errors"] == 1
    assert tracer.steps[0].error == "Provider unavailable"


def test_tracer_saves_valid_json(tmp_path):
    tracer = Tracer()
    tracer.record_tool_call("git_status", {})

    path = tracer.save(tmp_path)

    assert path is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["steps"][0]["type"] == "tool_call"
    assert data["summary"]["total_tool_calls"] == 1


def test_trace_redacts_tool_arguments(tmp_path):
    tracer = Tracer()
    tracer.record_tool_call(
        "read_file",
        {"path": "private_config.env", "token": "example-secret"},
    )

    path = tracer.save(tmp_path)
    assert path is not None

    content = path.read_text(encoding="utf-8")
    assert "example-secret" not in content
    assert "private_config.env" not in content