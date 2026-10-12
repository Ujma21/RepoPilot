
from dataclasses import dataclass, field


DEFAULT_MAX_STEPS = 5
DEFAULT_MAX_TOOL_CALLS = 20


@dataclass(frozen=True)
class SafetyPolicy:
    """Define the actions RepoPilot is allowed to perform."""

    allowed_tools: frozenset[str] = field(
        default_factory=lambda: frozenset({"git_status"})
    )
    max_steps: int = DEFAULT_MAX_STEPS
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1.")

        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be at least 1.")

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Return whether a tool is explicitly allowlisted."""
        return tool_name in self.allowed_tools
