
import subprocess

from repopilot.tools.git_tools import execute_tool, git_status
from pathlib import Path

def test_git_status_reports_repository_root(tmp_path):
    subprocess.run(
        ["git", "init", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    original_directory = __import__("os").getcwd()

    try:
        __import__("os").chdir(tmp_path)
        result = git_status()
    finally:
        __import__("os").chdir(original_directory)

    assert result["success"] is True
    assert Path(result["repository_root"]) == tmp_path


def test_git_status_rejects_unknown_tool():
    result = execute_tool("delete_repository", {})

    assert result["success"] is False
    assert "Unknown tool" in result["error"]


def test_git_status_rejects_arguments():
    result = execute_tool("git_status", {"command": "git push"})

    assert result["success"] is False
    assert "does not accept arguments" in result["error"]