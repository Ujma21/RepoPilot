
from types import SimpleNamespace

import pytest

from repopilot.providers.base import LLMProvider
from repopilot.providers.gemini_adapter import GeminiAdapter


import json


def test_provider_interface_requires_both_methods():
    with pytest.raises(TypeError):
        LLMProvider()


def test_convert_messages_separates_system_instruction():
    system, contents = GeminiAdapter._convert_messages(
        [
            {"role": "system", "content": "You are RepoPilot."},
            {"role": "user", "content": "Check my repository."},
            {"role": "assistant", "content": "I will check it."},
        ]
    )

    assert system == "You are RepoPilot."
    assert len(contents) == 2
    assert contents[0].role == "user"
    assert contents[1].role == "model"





def test_convert_messages_supports_tool_result_history():
    system, contents = GeminiAdapter._convert_messages(
        [
            {"role": "user", "content": "Check the repository."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "git_status",
                        "arguments": {},
                    }
                ],
            },
            {
                "role": "tool",
                "name": "git_status",
                "tool_call_id": "call_1",
                "content": json.dumps(
                    {
                        "success": True,
                        "status": "## main",
                    }
                ),
            },
        ]
    )

    assert system is None
    assert len(contents) == 3

    # The assistant message preserves its function call.
    assistant_parts = contents[1].parts
    assert assistant_parts[0].function_call.name == "git_status"

    # The tool result becomes a Gemini function response.
    result_part = contents[2].parts[0]
    assert result_part.function_response.name == "git_status"
    assert result_part.function_response.response["success"] is True


def test_chat_returns_model_text():
    adapter = GeminiAdapter.__new__(GeminiAdapter)
    adapter.model = "test-model"

    adapter.client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(
                text="The repository is clean."
            )
        )
    )

    result = adapter.chat(
        [{"role": "user", "content": "What is the repo state?"}]
    )

    assert result == "The repository is clean."


def test_chat_with_tools_normalizes_function_call():
    function_call = SimpleNamespace(
        name="git_status",
        args={},
    )
    part = SimpleNamespace(text=None, function_call=function_call)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    response = SimpleNamespace(candidates=[candidate])

    adapter = GeminiAdapter.__new__(GeminiAdapter)
    adapter.model = "test-model"

    adapter.client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: response
        )
    )

    result = adapter.chat_with_tools(
        [{"role": "user", "content": "Check the repo."}],
        [
            {
                "name": "git_status",
                "description": "Read repository status.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            }
        ],
    )

    assert result["text"] == ""
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "git_status"
    assert result["tool_calls"][0]["arguments"] == {}