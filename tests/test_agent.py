
import json
import pytest
from repopilot.core.agent import Agent


class FakeProvider:
    def __init__(self):
        self.responses = [
            {
                "text": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "git_status",
                        "arguments": {},
                    }
                ],
            },
            {
                "text": "The repository status was checked successfully.",
                "tool_calls": [],
            },
        ]
        self.last_messages = None

    def chat_with_tools(self, messages, tools):
        self.last_messages = messages
        return self.responses.pop(0)

    def chat(self, messages):
        self.last_messages = messages
        return "Final answer"


def test_agent_executes_tool_and_returns_final_answer():
    provider = FakeProvider()
    agent = Agent(provider=provider)

    answer = agent.run("Check my repository.")

    assert answer == "The repository status was checked successfully."
    assert provider.last_messages is not None

    tool_messages = [
        message
        for message in provider.last_messages
        if message["role"] == "tool"
    ]
    assert len(tool_messages) == 1

    result = json.loads(tool_messages[0]["content"])
    assert "success" in result


def test_agent_rejects_empty_question():
    agent = Agent(provider=FakeProvider())

    try:
        agent.run("   ")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Question cannot be empty" in str(exc)


def test_agent_rejects_invalid_step_limit():
    try:
        Agent(provider=FakeProvider(), max_steps=0)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "max_steps" in str(exc)


def test_agent_records_llm_failure():
    class FailingProvider:
        model = "test-model"

        def chat_with_tools(self, messages, tools):
            raise RuntimeError("Simulated provider failure")

        def chat(self, messages):
            raise RuntimeError("Simulated provider failure")

    agent = Agent(provider=FailingProvider())

    with pytest.raises(RuntimeError, match="Simulated provider failure"):
        agent.run("Check my repository.")

    assert agent.tracer is not None
    assert agent.tracer.summary()["total_errors"] == 1
    assert any(
        step.type == "llm_call"
        for step in agent.tracer.steps
    )


def test_agent_records_tool_failure(monkeypatch):
    import repopilot.core.agent as agent_module

    def failing_tool(name, arguments):
        raise RuntimeError("Simulated tool failure")

    monkeypatch.setattr(agent_module, "execute_tool", failing_tool)

    provider = FakeProvider()
    agent = Agent(provider=provider)

    answer = agent.run("Check my repository.")

    assert answer == "The repository status was checked successfully."
    assert agent.tracer is not None
    assert agent.tracer.summary()["total_errors"] == 1
    assert agent.tracer.summary()["total_tool_calls"] == 1

    tool_results = [
        step for step in agent.tracer.steps
        if step.type == "tool_result"
    ]
    assert len(tool_results) == 1
    assert tool_results[0].result["success"] is False


def test_trace_save_failure_does_not_break_agent(monkeypatch):
    from repopilot.core.tracing import Tracer

    def failing_save(self, directory=".runs"):
        return None

    monkeypatch.setattr(Tracer, "save", failing_save)

    agent = Agent(provider=FakeProvider())
    answer = agent.run("Check my repository.")

    assert answer == "The repository status was checked successfully."