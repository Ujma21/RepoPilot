
from __future__ import annotations

import base64
import io
import os
import zipfile
from typing import Any
from urllib.parse import quote, urlparse

import httpx


class GitHubAPIError(RuntimeError):
    """Base exception for GitHub API failures."""


class GitHubAuthError(GitHubAPIError):
    """Authentication or permission failure."""


class GitHubNotFoundError(GitHubAPIError):
    """Requested GitHub resource was not found."""


class GitHubRateLimitError(GitHubAPIError):
    """GitHub API rate limit was reached."""


class GitHubNetworkError(GitHubAPIError):
    """Network or timeout failure while contacting GitHub."""


class GitHubClient:
    API_BASE_URL = "https://api.github.com"

    MAX_LOG_ARCHIVE_BYTES = 20 * 1024 * 1024
    MAX_EXTRACTED_LOG_BYTES = 30 * 1024 * 1024
    MAX_LOG_CHARS = 200_000

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RepoPilot",
        }

        resolved_token = token or os.getenv("GITHUB_TOKEN")
        if resolved_token:
            headers["Authorization"] = f"Bearer {resolved_token}"

        self._client = client or httpx.Client(
            base_url=self.API_BASE_URL,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )

    @staticmethod
    def _validate_repo(repo: str) -> str:
        parts = repo.split("/")
        if (
            len(parts) != 2
            or not all(parts)
            or any(part in {".", ".."} for part in parts)
            or any(any(char.isspace() for char in char_part) for char_part in parts)
        ):
            raise ValueError("repo must use the 'owner/repository' format.")
        return repo

    @staticmethod
    def _validate_id(value: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer.")

    def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise GitHubNetworkError("GitHub request timed out.") from exc
        except httpx.RequestError as exc:
            raise GitHubNetworkError("Could not connect to GitHub.") from exc

        if response.status_code == 401:
            raise GitHubAuthError(
                "GitHub authentication failed. Check GITHUB_TOKEN."
            )

        if response.status_code == 404:
            raise GitHubNotFoundError(
                "GitHub resource not found. Check the repository, ID, "
                "file path, and token permissions."
            )

        if response.status_code == 403 and (
            response.headers.get("X-RateLimit-Remaining") == "0"
            or "rate limit" in response.text.lower()
        ):
            reset = response.headers.get("X-RateLimit-Reset")
            suffix = f" Rate limit reset timestamp: {reset}." if reset else ""
            raise GitHubRateLimitError(
                f"GitHub API rate limit reached.{suffix}"
            )

        if response.status_code == 403:
            raise GitHubAuthError(
                "GitHub denied access. Check token permissions."
            )

        if response.is_error:
            raise GitHubAPIError(
                f"GitHub returned HTTP {response.status_code}."
            )

        return response

    def get_run(self, repo: str, run_id: int) -> dict[str, Any]:
        repo = self._validate_repo(repo)
        self._validate_id(run_id, "run_id")

        response = self._request(
            "GET", f"/repos/{repo}/actions/runs/{run_id}"
        )
        data = response.json()

        if not isinstance(data, dict):
            raise GitHubAPIError("Unexpected workflow-run response.")
        return data

    def get_jobs(self, repo: str, run_id: int) -> list[dict[str, Any]]:
        repo = self._validate_repo(repo)
        self._validate_id(run_id, "run_id")

        response = self._request(
            "GET",
            f"/repos/{repo}/actions/runs/{run_id}/jobs",
            params={"per_page": 100},
        )
        data = response.json()
        jobs = data.get("jobs") if isinstance(data, dict) else None

        if not isinstance(jobs, list):
            raise GitHubAPIError("Unexpected workflow-jobs response.")
        return [job for job in jobs if isinstance(job, dict)]

    def get_job_logs(self, repo: str, job_id: int) -> str:
        """Download and return bounded plain-text or ZIP job logs."""
        repo = self._validate_repo(repo)
        self._validate_id(job_id, "job_id")

        # Do not automatically follow the redirect using the authenticated
        # GitHub API client.
        response = self._request(
            "GET",
            f"/repos/{repo}/actions/jobs/{job_id}/logs",
            follow_redirects=False,
        )

        if response.status_code == 302:
            location = response.headers.get("location")
            if not location:
                raise GitHubAPIError(
                    "GitHub returned a redirect without a download URL."
                )

            parsed = urlparse(location)
            hostname = (parsed.hostname or "").lower()

            # Only allow HTTPS Azure Blob Storage download hosts.
            if (
                parsed.scheme != "https"
                or not hostname.endswith(".blob.core.windows.net")
                or parsed.username
                or parsed.password
            ):
                raise GitHubAPIError(
                    "GitHub returned an unexpected log-download host."
                )

            # Never forward the GitHub Authorization header to blob storage.
            try:
                with httpx.Client(
                    timeout=30.0,
                    follow_redirects=False,
                    headers={"User-Agent": "RepoPilot"},
                ) as download_client:
                    with download_client.stream(
                        "GET", location
                    ) as downloaded:
                        if not downloaded.is_success:
                            raise GitHubAPIError(
                                "Log download returned HTTP "
                                f"{downloaded.status_code}."
                            )

                        content_length = downloaded.headers.get(
                            "content-length"
                        )
                        if content_length:
                            try:
                                declared_size = int(content_length)
                            except ValueError:
                                declared_size = 0

                            if declared_size > self.MAX_LOG_ARCHIVE_BYTES:
                                raise GitHubAPIError(
                                    "Job log download exceeds the size limit."
                                )

                        download_buffer = bytearray()
                        for chunk in downloaded.iter_bytes():
                            download_buffer.extend(chunk)
                            if (
                                len(download_buffer)
                                > self.MAX_LOG_ARCHIVE_BYTES
                            ):
                                raise GitHubAPIError(
                                    "Job log download exceeds the size limit."
                                )

                        downloaded_bytes = bytes(download_buffer)

            except httpx.TimeoutException as exc:
                raise GitHubNetworkError(
                    "Job-log download timed out."
                ) from exc
            except httpx.RequestError as exc:
                raise GitHubNetworkError(
                    "Could not download the job logs."
                ) from exc

            content_type = downloaded.headers.get(
                "content-type", ""
            ).lower()

        elif response.status_code == 200:
            # Support direct responses, including existing mocked tests.
            downloaded_bytes = response.content
            content_type = response.headers.get(
                "content-type", ""
            ).lower()

        else:
            raise GitHubAPIError(
                "Unexpected HTTP status when requesting job logs: "
                f"{response.status_code}."
            )

        if len(downloaded_bytes) > self.MAX_LOG_ARCHIVE_BYTES:
            raise GitHubAPIError(
                "Job log download exceeds the size limit."
            )

        # GitHub's current download endpoint may return plain text directly.
        if content_type.startswith("text/plain"):
            combined = downloaded_bytes.decode(
                "utf-8-sig", errors="replace"
            )
        else:
            try:
                with zipfile.ZipFile(
                    io.BytesIO(downloaded_bytes)
                ) as archive:
                    pieces: list[str] = []
                    total_bytes = 0

                    for item in archive.infolist():
                        if item.is_dir() or not item.filename.lower().endswith(
                            (".txt", ".log")
                        ):
                            continue

                        total_bytes += item.file_size
                        if total_bytes > self.MAX_EXTRACTED_LOG_BYTES:
                            raise GitHubAPIError(
                                "Extracted job logs exceed the size limit."
                            )

                        with archive.open(item) as stream:
                            content = stream.read(
                                self.MAX_EXTRACTED_LOG_BYTES + 1
                            )

                        if len(content) > self.MAX_EXTRACTED_LOG_BYTES:
                            raise GitHubAPIError(
                                "An individual log file exceeds the size limit."
                            )

                        pieces.append(
                            f"===== {item.filename} =====\n"
                            + content.decode(
                                "utf-8-sig", errors="replace"
                            )
                        )

            except zipfile.BadZipFile as exc:
                raise GitHubAPIError(
                    "GitHub returned neither plain-text logs "
                    "nor a valid ZIP archive."
                ) from exc

            combined = "\n\n".join(pieces)

            if not combined:
                raise GitHubAPIError(
                    "The job-log archive contained no supported text files."
                )

        if not combined.strip():
            raise GitHubAPIError("The downloaded job logs are empty.")

        if len(combined) > self.MAX_LOG_CHARS:
            combined = combined[: self.MAX_LOG_CHARS] + (
                "\n\n[RepoPilot: log output truncated]"
            )

        return combined

    def get_workflow_file(self, repo: str, path: str) -> str:
        repo = self._validate_repo(repo)

        if not path or path.startswith("/") or "\x00" in path:
            raise ValueError(
                "path must be a non-empty repository-relative path."
            )

        encoded_path = quote(path, safe="/")
        response = self._request(
            "GET", f"/repos/{repo}/contents/{encoded_path}"
        )
        data = response.json()

        if not isinstance(data, dict) or data.get("type") != "file":
            raise GitHubAPIError(
                "The requested workflow path is not a file."
            )

        content = data.get("content")
        encoding = data.get("encoding")

        if not isinstance(content, str) or encoding != "base64":
            raise GitHubAPIError(
                "GitHub returned an unsupported file-content format."
            )

        try:
            return base64.b64decode(content, validate=False).decode(
                "utf-8", errors="replace"
            )
        except (ValueError, UnicodeError) as exc:
            raise GitHubAPIError(
                "Could not decode the repository file."
            ) from exc

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

