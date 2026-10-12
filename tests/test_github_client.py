
import base64
import io
import json
import zipfile

import httpx
import pytest

from repopilot.integrations.github_client import (
    GitHubAuthError,
    GitHubClient,
    GitHubNotFoundError,
    GitHubRateLimitError,
)


def make_client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(
        transport=transport,
        base_url=GitHubClient.API_BASE_URL,
        follow_redirects=True,
    )
    return GitHubClient(token="test-token", client=http), http


def test_get_run_returns_workflow_data():
    def handler(request):
        assert request.url.path == "/repos/octocat/demo/actions/runs/123"
        return httpx.Response(
            200,
            json={"id": 123, "status": "completed", "conclusion": "failure"},
        )

    client, http = make_client(handler)
    try:
        result = client.get_run("octocat/demo", 123)
        assert result["conclusion"] == "failure"
    finally:
        http.close()


def test_get_jobs_returns_job_list():
    def handler(request):
        return httpx.Response(
            200,
            json={"jobs": [{"id": 456, "name": "tests", "conclusion": "failure"}]},
        )

    client, http = make_client(handler)
    try:
        jobs = client.get_jobs("octocat/demo", 123)
        assert len(jobs) == 1
        assert jobs[0]["id"] == 456
    finally:
        http.close()


def test_get_job_logs_extracts_zip_archive():
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("0_Test step.txt", "ModuleNotFoundError: missing package")

    archive_bytes = archive_buffer.getvalue()

    def handler(request):
        return httpx.Response(
            200,
            content=archive_bytes,
            headers={"Content-Type": "application/zip"},
        )

    client, http = make_client(handler)
    try:
        logs = client.get_job_logs("octocat/demo", 456)
        assert "ModuleNotFoundError" in logs
        assert "0_Test step.txt" in logs
    finally:
        http.close()


def test_get_workflow_file_decodes_base64():
    encoded = base64.b64encode(
        b"name: CI\non: [push]\njobs: {}\n"
    ).decode()

    def handler(request):
        assert request.url.path.endswith("/contents/.github/workflows/ci.yml")
        return httpx.Response(
            200,
            json={
                "type": "file",
                "encoding": "base64",
                "content": encoded,
            },
        )

    client, http = make_client(handler)
    try:
        content = client.get_workflow_file(
            "octocat/demo", ".github/workflows/ci.yml"
        )
        assert "name: CI" in content
    finally:
        http.close()


@pytest.mark.parametrize(
    ("status", "headers", "expected_error"),
    [
        (401, {}, GitHubAuthError),
        (404, {}, GitHubNotFoundError),
        (403, {"X-RateLimit-Remaining": "0"}, GitHubRateLimitError),
    ],
)
def test_github_http_errors(status, headers, expected_error):
    def handler(request):
        return httpx.Response(status, headers=headers, json={"message": "error"})

    client, http = make_client(handler)
    try:
        with pytest.raises(expected_error):
            client.get_run("octocat/demo", 123)
    finally:
        http.close()


def test_invalid_repository_is_rejected():
    client, http = make_client(
        lambda request: httpx.Response(200, json={})
    )
    try:
        with pytest.raises(ValueError):
            client.get_run("not-a-valid-repository", 123)
    finally:
        http.close()
