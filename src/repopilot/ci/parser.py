
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from repopilot.ci.signals import FailureSignal


DEFAULT_PATTERNS_PATH = Path(__file__).with_name("patterns.yaml")
MAX_LOG_CHARS = 1_000_000
MAX_SIGNALS = 100
MAX_EXCERPT_CHARS = 500

# Common source locations, including Python tracebacks and JS stack traces.
LOCATION_PATTERNS = (
    re.compile(r'File "([^"]+)", line (\d+)'),
    re.compile(r"([\w./\\-]+\.[\w]+):(\d+)(?::\d+)?"),
)


def _load_patterns(path: Path) -> list[dict[str, Any]]:
    """Load and validate pattern definitions from YAML."""
    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except OSError as exc:
        raise ValueError(f"Could not read CI patterns file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError("CI patterns file contains invalid YAML.") from exc

    if not isinstance(data, dict) or not isinstance(data.get("patterns"), list):
        raise ValueError("CI patterns YAML must contain a 'patterns' list.")

    validated = []
    for item in data["patterns"]:
        if not isinstance(item, dict):
            raise ValueError("Each CI pattern must be a mapping.")

        pattern_type = item.get("type")
        message = item.get("message")
        regex = item.get("regex")
        confidence = item.get("confidence")

        if not all(isinstance(value, str) and value for value in (
            pattern_type, message, regex
        )):
            raise ValueError("Each CI pattern needs type, message, and regex.")

        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0.0 <= confidence <= 1.0
        ):
            raise ValueError(
                f"Pattern '{pattern_type}' has invalid confidence."
            )

        try:
            compiled = re.compile(regex)
        except re.error as exc:
            raise ValueError(
                f"Pattern '{pattern_type}' has an invalid regex."
            ) from exc

        validated.append({
            "type": pattern_type,
            "message": message,
            "confidence": float(confidence),
            "compiled": compiled,
        })

    return validated


def _find_location(
    line: str,
) -> tuple[str | None, int | None]:
    for pattern in LOCATION_PATTERNS:
        match = pattern.search(line)
        if match:
            try:
                return match.group(1), int(match.group(2))
            except ValueError:
                continue

    return None, None


def parse_log(
    log_text: str,
    patterns_path: str | Path | None = None,
) -> list[FailureSignal]:
    """Identify known failure signatures without using an LLM."""
    if not isinstance(log_text, str):
        raise TypeError("log_text must be a string.")

    if not log_text.strip():
        return []

    if len(log_text) > MAX_LOG_CHARS:
        log_text = log_text[:MAX_LOG_CHARS]

    path = Path(patterns_path) if patterns_path else DEFAULT_PATTERNS_PATH
    patterns = _load_patterns(path)
    lines = log_text.splitlines()
    signals: list[FailureSignal] = []
    seen: set[tuple[str, int]] = set()

    for index, line in enumerate(lines):
        for pattern in patterns:
            match = pattern["compiled"].search(line)
            if not match:
                continue

            key = (pattern["type"], index)
            if key in seen:
                continue
            seen.add(key)

            # Prefer a source location from the matched line, then nearby
            # traceback context, so a traceback followed by an error can
            # still report its source file and line.
            source_file, source_line = _find_location(line)
            if source_file is None:
                for nearby in reversed(lines[max(0, index - 8):index]):
                    source_file, source_line = _find_location(nearby)
                    if source_file is not None:
                        break

            message = pattern["message"]
            if match.lastindex:
                detail = match.group(1)
                if detail:
                    message = f"{message} Detail: {detail.strip()}"

            start = max(0, index - 1)
            end = min(len(lines), index + 2)
            excerpt = "\n".join(lines[start:end])[:MAX_EXCERPT_CHARS]

            signals.append(
                FailureSignal(
                    type=pattern["type"],
                    message=message,
                    file=source_file,
                    line=source_line,
                    raw_excerpt=excerpt,
                    confidence=pattern["confidence"],
                )
            )

            if len(signals) >= MAX_SIGNALS:
                return signals

    return signals
