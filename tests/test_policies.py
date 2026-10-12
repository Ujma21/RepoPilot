
import pytest

from repopilot.safety.policies import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOOL_CALLS,
    SafetyPolicy,
)


def test_default_policy_limits():
    policy = SafetyPolicy()

    assert policy.max_steps == DEFAULT_MAX_STEPS
    assert policy.max_tool_calls == DEFAULT_MAX_TOOL_CALLS


def test_git_status_is_allowed_by_default():
    policy = SafetyPolicy()

    assert policy.is_tool_allowed("git_status") is True


def test_unknown_tool_is_rejected_by_policy():
    policy = SafetyPolicy()

    assert policy.is_tool_allowed("delete_files") is False
    assert policy.is_tool_allowed("run_shell_command") is False


def test_custom_allowlist():
    policy = SafetyPolicy(
        allowed_tools=frozenset({"git_status", "read_file"})
    )

    assert policy.is_tool_allowed("read_file") is True
    assert policy.is_tool_allowed("push_changes") is False


def test_max_steps_must_be_positive():
    with pytest.raises(ValueError):
        SafetyPolicy(max_steps=0)


def test_max_tool_calls_must_be_positive():
    with pytest.raises(ValueError):
        SafetyPolicy(max_tool_calls=0)
