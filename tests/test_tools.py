
import subprocess
from pathlib import Path

from repopilot.tools.git_tools import (
    MAX_SOURCE_FILE_BYTES,
    execute_tool,
    git_status,
    list_repo_files,
    read_repo_file,
)


def init_repo(path: Path) -> None:
    """Create a temporary Git repository for testing."""
    subprocess.run(
        ["git", "init", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_git_status_reports_repository_root(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = git_status()

    assert result["success"] is True
    assert Path(result["repository_root"]) == tmp_path.resolve()


def test_git_status_rejects_unknown_tool():
    result = execute_tool("delete_repository", {})

    assert result["success"] is False
    assert "Unknown tool" in result["error"]


def test_git_status_rejects_arguments():
    result = execute_tool("git_status", {"command": "git push"})

    assert result["success"] is False
    assert "does not accept arguments" in result["error"]


def test_list_repo_files_lists_source_files(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("print('hello')", encoding="utf-8")

    result = list_repo_files()

    assert result["success"] is True
    assert "src/app.py" in result["files"]
    assert result["count"] >= 1


def test_list_repo_files_excludes_env_file(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    (tmp_path / ".env").write_text(
        "API_TOKEN=example-secret",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "print('hello')",
        encoding="utf-8",
    )

    result = list_repo_files()

    assert result["success"] is True
    assert ".env" not in result["files"]
    assert "main.py" in result["files"]


def test_read_repo_file_reads_valid_source(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    source = tmp_path / "main.py"
    source.write_text("print('hello')", encoding="utf-8")

    result = read_repo_file({"path": "main.py"})

    assert result["success"] is True
    assert result["content"] == "print('hello')"
    assert result["path"] == "main.py"


def test_read_repo_file_rejects_path_traversal(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = read_repo_file({"path": "../outside.txt"})

    assert result["success"] is False
    assert "relative path" in result["error"]


def test_read_repo_file_rejects_absolute_path(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = read_repo_file({"path": str(tmp_path / "main.py")})

    assert result["success"] is False
    assert "relative path" in result["error"]


def test_read_repo_file_blocks_env(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    (tmp_path / ".env").write_text(
        "API_TOKEN=example-secret",
        encoding="utf-8",
    )

    result = read_repo_file({"path": ".env"})

    assert result["success"] is False
    assert "blocked" in result["error"]


def test_read_repo_file_rejects_missing_file(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = read_repo_file({"path": "missing.py"})

    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_read_repo_file_rejects_binary_file(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "image.bin").write_bytes(b"\x00\x01\x02")

    result = read_repo_file({"path": "image.bin"})

    assert result["success"] is False
    assert "Binary files" in result["error"]


def test_read_repo_file_rejects_oversized_file(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"x" * (MAX_SOURCE_FILE_BYTES + 1))

    result = read_repo_file({"path": "large.txt"})

    assert result["success"] is False
    assert "exceeds" in result["error"]


def test_read_repo_file_rejects_unexpected_arguments(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = read_repo_file({
        "path": "main.py",
        "command": "git push",
    })

    assert result["success"] is False
    assert "exactly one argument" in result["error"]


def test_execute_tool_dispatches_list_repo_files(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = execute_tool("list_repo_files", {})

    assert result["success"] is True
    assert result["files"] == []


def test_execute_tool_rejects_list_arguments():
    result = execute_tool("list_repo_files", {"path": "main.py"})

    assert result["success"] is False
    assert "does not accept arguments" in result["error"]


def test_execute_tool_dispatches_read_repo_file(tmp_path, monkeypatch):
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    (tmp_path / "main.py").write_text(
        "print('ok')",
        encoding="utf-8",
    )

    result = execute_tool(
        "read_repo_file",
        {"path": "main.py"},
    )

    assert result["success"] is True
    assert result["content"] == "print('ok')"
