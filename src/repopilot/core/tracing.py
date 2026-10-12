
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class AgentStep:
    """One observable event during a RepoPilot run."""

    step_number: int
    timestamp: str
    type: str
    model: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    result: Any | None = None
    error: str | None = None
    duration_ms: float = 0.0
    tokens_used: int | None = None


class Tracer:
    """Collect provider-independent events for one agent run."""

    def __init__(self) -> None:
        self.steps: list[AgentStep] = []
        self.started_at = time.monotonic()
        self.run_id = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S_%fZ"
        )

    def _record(self, event_type: str, **kwargs: Any) -> None:
        try:
            step = AgentStep(
                step_number=len(self.steps) + 1,
                timestamp=datetime.now(timezone.utc).isoformat(),
                type=event_type,
                **kwargs,
            )
            self.steps.append(step)
        except Exception:
            # Observability must not interrupt agent execution.
            pass

    def record_llm_call(
        self,
        model: str | None,
        duration_ms: float,
        tokens_used: int | None = None,
    ) -> None:
        self._record(
            "llm_call",
            model=model,
            duration_ms=round(duration_ms, 2),
            tokens_used=tokens_used,
        )

    
    def record_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        # Store only the tool name, not potentially sensitive arguments.
        self._record(
            "tool_call",
            tool_name=tool_name,
            arguments={"redacted": True} if arguments else {},
        )

    def record_tool_result(
        self,
        tool_name: str,
        result: dict[str, Any],
        duration_ms: float,
    ) -> None:
        # Record a bounded summary instead of unrestricted tool output.
        safe_result = {
            "success": result.get("success"),
            "error": str(result.get("error", ""))[:500]
            if result.get("error")
            else None,
        }

        self._record(
            "tool_result",
            tool_name=tool_name,
            result=safe_result,
            duration_ms=round(duration_ms, 2),
        )

    
    def record_error(
        self,
        error: str,
        duration_ms: float = 0.0,
    ) -> None:
        # Avoid persisting exception messages that may contain sensitive data.
        self._record(
            "error",
            error=error[:200] if error else "Unknown error",
            duration_ms=round(duration_ms, 2),
        )

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "total_steps": len(self.steps),
            "total_llm_calls": sum(
                step.type == "llm_call" for step in self.steps
            ),
            "total_tool_calls": sum(
                step.type == "tool_call" for step in self.steps
            ),
            "total_tool_results": sum(
                step.type == "tool_result" for step in self.steps
            ),
            "total_errors": sum(
                step.type == "error" for step in self.steps
            ),
            "duration_seconds": round(
                time.monotonic() - self.started_at, 3
            ),
        }

    def save(self, directory: str | Path = ".runs") -> Path | None:
        """Save the trace without allowing file errors to crash the agent."""
        try:
            output_dir = Path(directory)
            output_dir.mkdir(parents=True, exist_ok=True)

            path = output_dir / f"{self.run_id}.json"
            payload = {
                "summary": self.summary(),
                "steps": [asdict(step) for step in self.steps],
            }

            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return path
        except (OSError, TypeError, ValueError):
            return None