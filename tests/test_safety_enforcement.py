
from repopilot.core.agent import Agent
from repopilot.providers.base import LLMProvider
from repopilot.safety.policies import SafetyPolicy


class FakeProvider(LLMProvider):
    """Return predefined responses without making API calls."""

    def __init__(self, responses):
        self.responses = iter(responses)

    def chat_with_tools(self, messages, tools):
        return next(self.responses)

    def chat(self, messages):
        return "Finished processing tool results."


def test_disallowed_tool_is_never_executed(monkeypatch):
    import repopilot.core.agent as agent_module

    executed_tools = []

    def fake_execute_tool(name, arguments):
        executed_tools.append(name)
        return {"success": True}

    monkeypatch.setattr(
        agent_module, "execute_tool", fake_execute_tool
    )

    provider = FakeProvider([
        {
            "text": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "delete_files",
                    "arguments": {},
                }
            ],
        },
        {"text": "Blocked tool was handled.", "tool_calls": []},
    ])

    agent = Agent(provider, safety_policy=SafetyPolicy())
    agent.run("Inspect the repository.")

    assert executed_tools == []


def test_tool_call_budget_is_enforced(monkeypatch):
    import repopilot.core.agent as agent_module

    executed_tools = []

    def fake_execute_tool(name, arguments):
        executed_tools.append(name)
        return {"success": True, "status": "clean"}

    monkeypatch.setattr(
        agent_module, "execute_tool", fake_execute_tool
    )

    provider = FakeProvider([
        {
            "text": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "git_status",
                    "arguments": {},
                },
                {
                    "id": "call-2",
                    "name": "git_status",
                    "arguments": {},
                },
            ],
        },
        {"text": "Budget enforced.", "tool_calls": []},
    ])

    policy = SafetyPolicy(max_tool_calls=1)
    agent = Agent(provider, safety_policy=policy)
    agent.run("Check repository status.")

    assert executed_tools == ["git_status"]
