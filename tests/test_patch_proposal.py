
import json

import pytest

from repopilot.patches.proposal import (
    ProposalValidationError,
    generate_patch_proposal,
    validate_diff,
)


class MockProvider:
    """Return a predictable response without making an LLM API call."""

    def __init__(self, response: str):
        self.response = response
        self.messages = None

    def chat(self, messages):
        self.messages = messages
        return self.response

    def chat_with_tools(self, messages, tools):
        raise AssertionError("This test should not call chat_with_tools.")


def valid_response():
    return json.dumps({
        "summary": "Fix greeting output",
        "rationale": "The output string needs correction.",
        "diff": (
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1 +1 @@\n"
            "-print('hello')\n"
            "+print('hello world')\n"
        ),
        "risks": "Low risk; verify expected output in tests.",
    })


def test_generate_patch_proposal_returns_structured_result():
    provider = MockProvider(valid_response())

    proposal = generate_patch_proposal(
        provider,
        "A test reports unexpected output.",
        {"src/app.py": "print('hello')\n"},
    )

    assert proposal.summary == "Fix greeting output"
    assert proposal.files == ("src/app.py",)
    assert "+print('hello world')" in proposal.diff
    assert provider.messages is not None
    prompt = provider.messages[0]["content"]
    assert "exactly one JSON object" in prompt
    assert all(field in prompt for field in ("summary", "rationale", "diff", "risks"))


def test_fenced_json_and_incidental_whitespace_are_accepted():
    provider = MockProvider("  \n```json\n" + valid_response() + "\n```\n  ")

    proposal = generate_patch_proposal(
        provider,
        "A test reports unexpected output.",
        {"src/app.py": "print('hello')\n"},
    )

    assert proposal.summary == "Fix greeting output"
    assert proposal.files == ("src/app.py",)


def test_invalid_json_is_rejected():
    provider = MockProvider("not JSON")

    with pytest.raises(ProposalValidationError, match="JSON object"):
        generate_patch_proposal(
            provider,
            "A test failed.",
            {"src/app.py": "print('hello')\n"},
        )


def test_missing_response_fields_are_rejected():
    provider = MockProvider(json.dumps({"summary": "Incomplete"}))

    with pytest.raises(ProposalValidationError, match="missing required"):
        generate_patch_proposal(
            provider,
            "A test failed.",
            {"src/app.py": "print('hello')\n"},
        )


def test_changes_to_unapproved_file_are_rejected():
    diff = (
        "--- a/src/other.py\n"
        "+++ b/src/other.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    with pytest.raises(ProposalValidationError, match="not supplied as evidence"):
        validate_diff(diff, {"src/app.py"})


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        ".env",
        "config/.env.production",
        "keys/private.pem",
        ".ssh/id_ed25519",
    ],
)
def test_unsafe_source_paths_are_rejected(path):
    provider = MockProvider(valid_response())

    with pytest.raises(ProposalValidationError):
        generate_patch_proposal(
            provider,
            "A test failed.",
            {path: "example"},
        )


def test_empty_diff_is_rejected():
    with pytest.raises(ProposalValidationError):
        validate_diff("", {"src/app.py"})


def test_new_file_creation_is_rejected():
    diff = (
        "--- /dev/null\n"
        "+++ b/src/new.py\n"
        "@@ -0,0 +1 @@\n"
        "+print('new')\n"
    )

    with pytest.raises(ProposalValidationError):
        validate_diff(diff, {"src/new.py"})


def test_proposal_generation_does_not_modify_source_file(tmp_path):
    source = tmp_path / "app.py"
    original = "print('hello')\n"
    source.write_text(original, encoding="utf-8")

    provider = MockProvider(valid_response())

    generate_patch_proposal(
        provider,
        "A test reports unexpected output.",
        {"src/app.py": original},
    )

    assert source.read_text(encoding="utf-8") == original
