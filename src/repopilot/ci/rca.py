
from dataclasses import dataclass

from repopilot.ci.signals import FailureSignal


@dataclass(frozen=True)
class RootCauseAnalysis:
    """An evidence-based explanation of a detected CI failure."""

    cause: str
    evidence: str
    affected_component: str
    recommended_action: str
    confidence: float


# These rules are deterministic: no source files are modified.
RCA_RULES: dict[str, tuple[str, str]] = {
    "module_not_found": (
        "A required module or package could not be found.",
        "Verify the import name and declare/install the required dependency "
        "using the project's existing dependency manager.",
    ),
    "npm_missing_script": (
        "The requested npm script is not defined in package.json.",
        "Check the script name and inspect package.json in the relevant "
        "frontend or backend directory.",
    ),
    "out_of_memory": (
        "The process likely exceeded its available memory.",
        "Inspect memory usage and CI resource limits. Review recent changes "
        "for unusually memory-intensive operations before changing limits.",
    ),
    "syntax_error": (
        "The runtime or parser encountered invalid syntax.",
        "Inspect the reported file and line, then correct the syntax using "
        "the surrounding code as context.",
    ),
    "test_failure": (
        "At least one test failed during CI execution.",
        "Inspect the failing test and its assertion output. Reproduce the "
        "failure locally before changing application code.",
    ),
    "git_pathspec": (
        "Git could not resolve the requested path or path specification.",
        "Check the path spelling, current working directory, and whether "
        "the referenced file or branch exists.",
    ),
    "permission_denied": (
        "The process was denied access to a resource.",
        "Check the resource path and the permissions of the CI user. Grant "
        "only the minimum permissions required.",
    ),
    "file_not_found": (
        "A required file or path could not be found.",
        "Verify the path, working directory, filename casing, and whether "
        "the file is available in the CI checkout.",
    ),
}


def analyze_signal(signal: FailureSignal) -> RootCauseAnalysis:
    """Explain one parsed failure signal without modifying the repository."""
    cause, action = RCA_RULES.get(
        signal.type,
        (
            f"An unclassified CI failure was detected: {signal.message}",
            "Review the evidence and surrounding CI logs to identify the "
            "underlying cause before making changes.",
        ),
    )

    if signal.file:
        component = signal.file
        if signal.line is not None:
            component = f"{component}:{signal.line}"
    else:
        component = "Not identified from the available log evidence"

    return RootCauseAnalysis(
        cause=cause,
        evidence=signal.raw_excerpt,
        affected_component=component,
        recommended_action=action,
        confidence=signal.confidence,
    )


def analyze_signals(
    signals: list[FailureSignal],
) -> list[RootCauseAnalysis]:
    """Analyze detected signals in their original order."""
    return [analyze_signal(signal) for signal in signals]
