
import subprocess
from pathlib import Path
from typing import Any


GIT_STATUS_TOOL = {
    "name": "git_status",
    "description": (
        "Read the current Git repository status, including the current "
        "branch and changed, staged, or untracked files. "
        "This tool is read-only and does not modify the repository."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


def git_status() -> dict[str, Any]:
    """Return the Git status of the current working directory."""
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.strip()
                or "Git status command failed.",
            }

        root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if root_result.returncode != 0:
            return {
                "success": False,
                "error": "Could not determine the repository root.",
            }

        status = result.stdout.strip()

        return {
            "success": True,
            "repository_root": root_result.stdout.strip(),
            "status": status or "Working tree clean.",
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": "Git was not found. Check that Git is installed and on PATH.",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Git status timed out.",
        }


def execute_tool(
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Validate and execute an available RepoPilot tool."""
    if name != "git_status":
        return {
            "success": False,
            "error": f"Unknown tool: {name}",
        }

    if arguments:
        return {
            "success": False,
            "error": "git_status does not accept arguments.",
        }

    return git_status()