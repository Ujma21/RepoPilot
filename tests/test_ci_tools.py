
from repopilot.tools import ci_tools


class FakeGitHubClient:
    def __init__(self):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def get_run(self, repo, run_id):
        return {
            "id": run_id,
            "status": "completed",
            "conclusion": "failure",
        }

    def get_jobs(self, repo, run_id):
        return [
            {
                "id": 456,
                "name": "Python tests",
                "conclusion": "failure",
            },
            {
                "id": 789,
                "name": "Build",
                "conclusion": "success",
            },
        ]

    def get_job_logs(self, repo, job_id):
        return "ModuleNotFoundError: missing package\n"


def test_fetch_ci_run_returns_failed_job_excerpt(monkeypatch):
    monkeypatch.setattr(
        ci_tools, "GitHubClient", FakeGitHubClient
    )

    result = ci_tools.fetch_ci_run({
        "repo": "octocat/demo",
        "run_id": 123,
    })

    assert result["success"] is True
    assert result["run_info"]["id"] == 123
    assert len(result["jobs"]) == 2
    assert len(result["log_excerpts"]) == 1
    assert result["log_excerpts"][0]["job_id"] == 456
    assert "ModuleNotFoundError" in result["log_excerpts"][0]["logs"]


def test_fetch_ci_logs_returns_logs_and_line_count(monkeypatch):
    monkeypatch.setattr(
        ci_tools, "GitHubClient", FakeGitHubClient
    )

    result = ci_tools.fetch_ci_logs({
        "repo": "octocat/demo",
        "job_id": 456,
    })

    assert result["success"] is True
    assert result["line_count"] == 1
    assert "ModuleNotFoundError" in result["logs"]
    assert result["truncated"] is False


def test_fetch_ci_run_rejects_invalid_run_id():
    result = ci_tools.fetch_ci_run({
        "repo": "octocat/demo",
        "run_id": True,
    })

    assert result["success"] is False
    assert "positive integer" in result["error"]


def test_fetch_ci_logs_rejects_missing_arguments():
    result = ci_tools.fetch_ci_logs({
        "repo": "octocat/demo",
    })

    assert result["success"] is False
    assert "job_id" in result["error"]


def test_fetch_ci_logs_truncates_large_output(monkeypatch):
    class LargeLogClient(FakeGitHubClient):
        def get_job_logs(self, repo, job_id):
            return "x" * (ci_tools.MAX_LOG_OUTPUT_CHARS + 100)

    monkeypatch.setattr(
        ci_tools, "GitHubClient", LargeLogClient
    )

    result = ci_tools.fetch_ci_logs({
        "repo": "octocat/demo",
        "job_id": 456,
    })

    assert result["success"] is True
    assert result["truncated"] is True
    assert len(result["logs"]) < (
        ci_tools.MAX_LOG_OUTPUT_CHARS + 100
    )
    assert result["line_count"] == 1
