
import json
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from repopilot.providers.base import LLMProvider


class GeminiAdapter(LLMProvider):
    """Gemini implementation of RepoPilot's provider interface."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        load_dotenv()

        resolved_key = api_key or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "GEMINI_API_KEY is missing. Add it to your local .env file."
            )

        self.model = model or os.getenv(
            "GEMINI_MODEL", "gemini-3.8-flash"
        )
        self.client = genai.Client(api_key=resolved_key)

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[types.Content]]:
        """Convert normalized RepoPilot history into Gemini contents."""
        system_parts: list[str] = []
        contents: list[types.Content] = []

        for message in messages:
            role = message["role"]
            content = message.get("content", "")

            if role == "system":
                system_parts.append(str(content))
                continue

            if role == "tool":
                tool_name = message.get("name")
                if not tool_name:
                    raise ValueError(
                        "Tool-result messages must include a tool name."
                    )

                try:
                    result = json.loads(str(content))
                except (json.JSONDecodeError, TypeError):
                    result = {"result": str(content)}

                function_response = types.FunctionResponse(
                    name=tool_name,
                    response=(
                        result
                        if isinstance(result, dict)
                        else {"result": result}
                    ),
                    id=message.get("tool_call_id") or None,
                )

                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=function_response
                            )
                        ],
                    )
                )
                continue

            if role not in ("user", "assistant"):
                raise ValueError(f"Unsupported message role: {role}")

            gemini_role = "model" if role == "assistant" else "user"
            parts: list[types.Part] = []

            if content:
                parts.append(types.Part(text=str(content)))

            if role == "assistant":
                for call in message.get("tool_calls", []):
                    function_call = types.FunctionCall(
                        name=call["name"],
                        args=call.get("arguments", {}),
                        id=call.get("id") or None,
                    )

                    part_kwargs: dict[str, Any] = {
                        "function_call": function_call
                    }

                    signature = call.get("thought_signature")
                    if signature:
                        part_kwargs["thought_signature"] = signature

                    parts.append(types.Part(**part_kwargs))

            if parts:
                contents.append(
                    types.Content(role=gemini_role, parts=parts)
                )

        system_instruction = "\n\n".join(system_parts) or None
        return system_instruction, contents

    def chat(self, messages: list[dict[str, str]]) -> str:
        system_instruction, contents = self._convert_messages(messages)

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
            ),
        )

        text = response.text
        if not text:
            raise RuntimeError("Gemini returned an empty text response.")

        return text

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system_instruction, contents = self._convert_messages(messages)

        declarations = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool.get(
                    "parameters",
                    {
                        "type": "object",
                        "properties": {},
                    },
                ),
            }
            for tool in tools
        ]

        gemini_tools = (
            [types.Tool(function_declarations=declarations)]
            if declarations
            else None
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=gemini_tools,
                temperature=0.2,
            ),
        )

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for candidate in response.candidates or []:
            if not candidate.content:
                continue

            for part in candidate.content.parts or []:
                if part.text:
                    text_parts.append(part.text)

                function_call = part.function_call
                if function_call and function_call.name:
                    arguments = function_call.args or {}

                    if isinstance(arguments, str):
                        arguments = json.loads(arguments)

                    tool_calls.append(
                        {
                            "id": (
                                getattr(function_call, "id", None)
                                or f"call_{len(tool_calls) + 1}"
                            ),
                            "name": function_call.name,
                            "arguments": dict(arguments),
                            "thought_signature": getattr(
                                part, "thought_signature", None
                            ),
                        }
                    )

        return {
            "text": "\n".join(text_parts),
            "tool_calls": tool_calls,
        }