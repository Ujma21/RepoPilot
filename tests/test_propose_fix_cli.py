import pytest

from repopilot import main
from repopilot.integrations.github_client import GitHubAPIError
from repopilot.patches.proposal import ProposalValidationError


class FakeClient:
    def __init__(self, error=None, repository="octocat/demo"):
        self.error = error
        self.repository = repository

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_run(self, repo, run_id):
        if self.error:
            raise self.error
        return {"repository": {"full_name": self.repository}}

    def get_jobs(self, repo, run_id):
        return [{"id": 41, "name": "tests", "conclusion": "failure"}]

    def get_job_logs(self, repo, job_id):
        return "ModuleNotFoundError: No module named 'widget'"


class FakeProvider:
    def chat(self, messages):
        return "{}"


def setup_cli(monkeypatch, tmp_path, proposal=None, client=None):
    monkeypatch.setattr(main, "_github_repository", lambda path: "octocat/demo")
    monkeypatch.setattr(main, "GitHubClient", lambda: client or FakeClient())
    monkeypatch.setattr(main, "GeminiAdapter", FakeProvider)
    monkeypatch.setattr(main, "list_repo_files", lambda: {"success": True, "files": ["src/app.py"]})
    original = "print('before')\n"
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text(original, encoding="utf-8")
    monkeypatch.setattr(main, "read_repo_file", lambda args: {"success": True, "path": args["path"], "content": original})
    monkeypatch.setattr(main, "generate_patch_proposal", lambda *args: proposal)
    return source, original


def valid_proposal():
    return type("Proposal", (), {
        "summary": "Fix missing module usage",
        "rationale": "The import is unavailable in CI.",
        "files": ("src/app.py",),
        "diff": "--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-old\n+new\n",
        "risks": "May affect callers.",
    })()


def test_propose_fix_parses_arguments_and_prints_proposal(monkeypatch, tmp_path, capsys):
    source, original = setup_cli(monkeypatch, tmp_path, valid_proposal())
    assert main.propose_fix(["--repo", str(tmp_path), "--run-id", "38234354621"]) == 0
    output = capsys.readouterr().out
    assert "Failure summary" in output
    assert "Fix missing module usage" in output
    assert "Rationale" in output and "Unified diff" in output and "Risks" in output
    assert source.read_text(encoding="utf-8") == original


def test_main_dispatches_propose_fix(monkeypatch):
    called = []
    monkeypatch.setattr(main, "propose_fix", lambda argv: called.append(argv) or 0)
    monkeypatch.setattr("sys.argv", ["repopilot", "propose-fix", "--repo", ".", "--run-id", "1"])
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0
    assert called == [["--repo", ".", "--run-id", "1"]]


def test_propose_fix_requires_repository_and_run_id():
    with pytest.raises(SystemExit) as exc:
        main.propose_fix([])
    assert exc.value.code == 2


def test_github_error_returns_nonzero(monkeypatch, tmp_path, capsys):
    setup_cli(monkeypatch, tmp_path, client=FakeClient(error=GitHubAPIError("API unavailable")))
    assert main.propose_fix(["--repo", str(tmp_path), "--run-id", "5"]) == 1
    assert "API unavailable" in capsys.readouterr().err


def test_validation_error_returns_nonzero(monkeypatch, tmp_path, capsys):
    setup_cli(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "generate_patch_proposal", lambda *args: (_ for _ in ()).throw(ProposalValidationError("invalid diff")))
    assert main.propose_fix(["--repo", str(tmp_path), "--run-id", "5"]) == 1
    assert "proposal validation error" in capsys.readouterr().err


def test_repository_mismatch_stops_before_logs(monkeypatch, tmp_path, capsys):
    client = FakeClient(repository="another/project")
    setup_cli(monkeypatch, tmp_path, client=client)
    assert main.propose_fix(["--repo", str(tmp_path), "--run-id", "5"]) == 1
    assert "Repository mismatch" in capsys.readouterr().err

