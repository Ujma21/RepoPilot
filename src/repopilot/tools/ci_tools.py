
from __future__ import annotations

from typing import Any

from repopilot.integrations.github_client import GitHubClient


MAX_FAILED_JOBS_TO_INSPECT = 5
MAX_EXCERPT_CHARS = 6_000
MAX_LOG_OUTPUT_CHARS = 20_000


FETCH_CI_RUN_TOOL = {
    "name": "fetch_ci_run",
    "description": (
        "Fetch a GitHub Actions workflow run, its jobs, and bounded "
        "log excerpts for failed jobs. This tool is read-only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "GitHub repository in owner/repository format.",
            },
            "run_id": {
                "type": "integer",
                "description": "GitHub Actions workflow run ID.",
            },
        },
        "required": ["repo", "run_id"],
    },
}

FETCH_CI_LOGS_TOOL = {
    "name": "fetch_ci_logs",
    "description": (
        "Fetch bounded logs for one GitHub Actions job and report "
        "the number of lines. This tool is read-only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "repo": {
                "type": "string",
                "description": "GitHub repository in owner/repository format.",
            },
            "job_id": {
                "type": "integer",
                "description": "GitHub Actions job ID.",
            },
        },
        "required": ["repo", "job_id"],
    },
}


def _validate_arguments(
    arguments: dict[str, Any],
    required: set[str],
) -> str | None:
    if set(arguments) != required:
        return (
            "Invalid arguments. Expected exactly: "
            + ", ".join(sorted(required))
        )

    repo = arguments.get("repo")
    if not isinstance(repo, str) or not repo.strip():
        return "repo must be a non-empty string."

    return None


def fetch_ci_run(arguments: dict[str, Any]) -> dict[str, Any]:
    """Fetch a workflow run, jobs, and bounded excerpts from failed jobs."""
    error = _validate_arguments(arguments, {"repo", "run_id"})
    if error:
        return {"success": False, "error": error}

    run_id = arguments["run_id"]
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        return {"success": False, "error": "run_id must be a positive integer."}

    repo = arguments["repo"].strip()

    try:
        with GitHubClient() as client:
            run_info = client.get_run(repo, run_id)
            jobs = client.get_jobs(repo, run_id)

            excerpts: list[dict[str, Any]] = []
            failed_jobs = [
                job for job in jobs
                if job.get("conclusion") == "failure"
            ]

            for job in failed_jobs[:MAX_FAILED_JOBS_TO_INSPECT]:
                job_id = job.get("id")

                if (
                    isinstance(job_id, bool)
                    or not isinstance(job_id, int)
                    or job_id <= 0
                ):
                    continue

                try:
                    logs = client.get_job_logs(repo, job_id)
                    excerpt = logs[:MAX_EXCERPT_CHARS]

                    if len(logs) > MAX_EXCERPT_CHARS:
                        excerpt += "\n[RepoPilot: excerpt truncated]"

                    excerpts.append({
                        "job_id": job_id,
                        "job_name": job.get("name", "Unknown job"),
                        "logs": excerpt,
                    })
                except Exception as exc:
                    # Preserve run/job metadata if one log download fails.
                    excerpts.append({
                        "job_id": job_id,
                        "job_name": job.get("name", "Unknown job"),
                        "error": f"{type(exc).__name__}: {exc}",
                    })

        return {
            "success": True,
            "run_info": run_info,
            "jobs": jobs,
            "log_excerpts": excerpts,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_ci_logs(arguments: dict[str, Any]) -> dict[str, Any]:
    """Fetch logs for one job, with a bounded output size."""
    error = _validate_arguments(arguments, {"repo", "job_id"})
    if error:
        return {"success": False, "error": error}

    job_id = arguments["job_id"]
    if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
        return {"success": False, "error": "job_id must be a positive integer."}

    repo = arguments["repo"].strip()

    try:
        with GitHubClient() as client:
            logs = client.get_job_logs(repo, job_id)

        line_count = len(logs.splitlines())
        truncated = len(logs) > MAX_LOG_OUTPUT_CHARS

        if truncated:
            logs = logs[:MAX_LOG_OUTPUT_CHARS]
            logs += "\n[RepoPilot: log output truncated]"

        return {
            "success": True,
            "logs": logs,
            "line_count": line_count,
            "truncated": truncated,
        }

    except Exception as exc:
        return {
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
