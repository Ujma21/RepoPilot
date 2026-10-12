
from dataclasses import dataclass


@dataclass(frozen=True)
class FailureSignal:
    """A failure identified in CI log output."""

    type: str
    message: str
    file: str | None
    line: int | None
    raw_excerpt: str
    confidence: float

    def __post_init__(self) -> None:
        if not self.type.strip():
            raise ValueError("Failure signal type cannot be empty.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0.")
        if self.line is not None and self.line < 1:
            raise ValueError("Line number must be positive.")
