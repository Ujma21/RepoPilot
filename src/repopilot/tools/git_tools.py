
import subprocess
from pathlib import Path
from typing import Any

from repopilot.tools.ci_tools import (
    FETCH_CI_LOGS_TOOL,
    FETCH_CI_RUN_TOOL,
    fetch_ci_logs,
    fetch_ci_run,
)

MAX_SOURCE_FILE_BYTES = 100 * 1024

GIT_STATUS_TOOL = {
    "name": "git_status",
    "description": (
        "Read the current Git repository status, including branch and "
        "changed, staged, or untracked files. Does not modify files."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

LIST_REPO_FILES_TOOL = {
    "name": "list_repo_files",
    "description": (
        "List tracked and non-ignored untracked repository files. "
        "Sensitive files and directories are excluded."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

READ_REPO_FILE_TOOL = {
    "name": "read_repo_file",
    "description": (
        "Read a permitted text file inside the current Git repository. "
        "Requires a relative path. Sensitive files are blocked."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Repository-relative file path.",
            }
        },
        "required": ["path"],
    },
}

BLOCKED_DIRS = {
    ".git",
    ".ssh",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
}

BLOCKED_NAMES = {
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "secrets",
}

ALLOWED_ENV_EXAMPLES = {
    ".env.example",
    ".env.sample",
    ".env.template",
}

BLOCKED_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}


def _repository_root() -> Path:
    """Return the root of the current Git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "Not inside a Git repository."
        )

    return Path(result.stdout.strip()).resolve()


def _is_sensitive_path(relative_path: Path) -> bool:
    """Identify paths that inspection tools must not expose."""
    parts = relative_path.parts

    if any(part.lower() in BLOCKED_DIRS for part in parts):
        return True

    name = relative_path.name.lower()

    if name in ALLOWED_ENV_EXAMPLES:
        return False

    if name in BLOCKED_NAMES:
        return True

    if name.startswith(".env."):
        return True

    if relative_path.suffix.lower() in BLOCKED_SUFFIXES:
        return True

    return False


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

        root = _repository_root()
        status = result.stdout.strip()

        return {
            "success": True,
            "repository_root": str(root),
            "status": status or "Working tree clean.",
        }

    except FileNotFoundError:
        return {
            "success": False,
            "error": "Git was not found. Check that Git is installed and on PATH.",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Git status timed out."}
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}


def list_repo_files() -> dict[str, Any]:
    """List repository files without exposing known sensitive paths."""
    try:
        root = _repository_root()

        result = subprocess.run(
            [
                "git",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            cwd=root,
            capture_output=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.decode(
                    "utf-8", errors="replace"
                ).strip() or "Could not list repository files.",
            }

        paths = []
        for item in result.stdout.decode(
            "utf-8", errors="replace"
        ).split("\0"):
            if not item:
                continue

            relative = Path(item)

            if not _is_sensitive_path(relative):
                paths.append(relative.as_posix())

        return {
            "success": True,
            "repository_root": str(root),
            "files": sorted(paths),
            "count": len(paths),
        }

    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "error": str(exc)}


def read_repo_file(arguments: dict[str, Any]) -> dict[str, Any]:
    """Read a bounded text file inside the repository."""
    if set(arguments) != {"path"}:
        return {
            "success": False,
            "error": "Expected exactly one argument: path.",
        }

    raw_path = arguments.get("path")

    if not isinstance(raw_path, str) or not raw_path.strip():
        return {
            "success": False,
            "error": "path must be a non-empty string.",
        }

    requested = Path(raw_path)

    if requested.is_absolute() or ".." in requested.parts:
        return {
            "success": False,
            "error": "Use a repository-relative path without '..'.",
        }

    if _is_sensitive_path(requested):
        return {
            "success": False,
            "error": "Access to this path is blocked by the safety policy.",
        }

    try:
        root = _repository_root()
        target = (root / requested).resolve(strict=True)

        if not target.is_relative_to(root):
            return {
                "success": False,
                "error": "The requested path is outside the repository.",
            }

        relative = target.relative_to(root)

        # Check again after resolving symlinks.
        if _is_sensitive_path(relative):
            return {
                "success": False,
                "error": "Access to this path is blocked by the safety policy.",
            }

        if not target.is_file():
            return {
                "success": False,
                "error": "The requested path is not a regular file.",
            }

        size = target.stat().st_size

        if size > MAX_SOURCE_FILE_BYTES:
            return {
                "success": False,
                "error": (
                    f"File exceeds the {MAX_SOURCE_FILE_BYTES}-byte limit."
                ),
            }

        content = target.read_bytes()

        if b"\0" in content:
            return {
                "success": False,
                "error": "Binary files cannot be read by this tool.",
            }

        return {
            "success": True,
            "path": relative.as_posix(),
            "size_bytes": len(content),
            "content": content.decode("utf-8", errors="replace"),
        }

    except FileNotFoundError:
        return {"success": False, "error": "File not found."}
    except PermissionError:
        return {"success": False, "error": "Permission denied."}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Git command timed out."}
    except RuntimeError as exc:
        return {"success": False, "error": str(exc)}
    except OSError as exc:
        return {"success": False, "error": f"Could not read file: {exc}"}


def execute_tool(
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Validate and execute an available RepoPilot tool."""
    if not isinstance(arguments, dict):
        return {
            "success": False,
            "error": "Tool arguments must be an object.",
        }

    if name == "git_status":
        if arguments:
            return {
                "success": False,
                "error": "git_status does not accept arguments.",
            }
        return git_status()

    if name == "list_repo_files":
        if arguments:
            return {
                "success": False,
                "error": "list_repo_files does not accept arguments.",
            }
        return list_repo_files()

    if name == "read_repo_file":
        return read_repo_file(arguments)

    if name == "fetch_ci_run":
        return fetch_ci_run(arguments)

    if name == "fetch_ci_logs":
        return fetch_ci_logs(arguments)

    return {
        "success": False,
        "error": f"Unknown tool: {name}",
    }
