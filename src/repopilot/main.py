
import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from repopilot.core.agent import Agent
from repopilot.providers.gemini_adapter import GeminiAdapter
from repopilot.ci.parser import parse_log
from repopilot.ci.rca import analyze_signal
from repopilot.integrations.github_client import GitHubAPIError, GitHubClient
from repopilot.patches.proposal import (
    ProposalValidationError,
    generate_patch_proposal,
)
from repopilot.tools.git_tools import list_repo_files, read_repo_file


MAX_FAILED_JOBS_TO_INSPECT = 5


def _github_repository(repo_path: Path) -> str:
    """Resolve the GitHub owner/repository from the local origin URL."""
    import subprocess

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=repo_path,
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode:
        raise ValueError("Could not identify the GitHub repository from origin.")
    remote = result.stdout.strip()
    match = re.search(r"(?:github\.com[:/])([^/]+/[^/]+?)(?:\.git)?$", remote)
    if not match:
        raise ValueError("The repository origin is not a GitHub URL.")
    return match.group(1)


def propose_fix(argv: list[str]) -> int:
    """Generate a read-only patch proposal for a GitHub Actions failure."""
    load_dotenv()
    parser = argparse.ArgumentParser(prog="repopilot propose-fix")
    parser.add_argument("--repo", required=True, help="Local repository directory.")
    parser.add_argument("--run-id", required=True, type=int, help="GitHub Actions run ID.")
    args = parser.parse_args(argv)
    if args.run_id <= 0:
        parser.error("--run-id must be a positive integer.")

    repo_path = Path(args.repo).expanduser().resolve()
    if not repo_path.is_dir():
        print(f"RepoPilot propose-fix error: repository directory does not exist: {repo_path}", file=sys.stderr)
        return 1

    try:
        github_repo = _github_repository(repo_path)
        with GitHubClient() as client:
            run_info = client.get_run(github_repo, args.run_id)
            remote_repo = (run_info.get("repository") or {}).get("full_name")
            if remote_repo and remote_repo.casefold() != github_repo.casefold():
                print(f"Repository mismatch: run belongs to {remote_repo}, but --repo origin is {github_repo}.", file=sys.stderr)
                return 1
            jobs = client.get_jobs(github_repo, args.run_id)
            failed_jobs = [job for job in jobs if job.get("conclusion") == "failure"]
            if not failed_jobs:
                print("No failed jobs were found in this run.", file=sys.stderr)
                return 1

            signals = []
            for job in failed_jobs[:MAX_FAILED_JOBS_TO_INSPECT]:
                job_id = job.get("id")
                if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
                    continue
                logs = client.get_job_logs(github_repo, job_id)
                signals.extend(parse_log(logs))

        if not signals:
            print("No recognized failure signatures were found in the run logs.", file=sys.stderr)
            return 1

        analyses = [analyze_signal(signal) for signal in signals]
        evidence = "\n\n".join(
            f"Failure: {signal.type}: {signal.message}\n"
            f"Root cause: {analysis.cause}\nEvidence: {signal.raw_excerpt}"
            for signal, analysis in zip(signals, analyses)
        )

        old_cwd = Path.cwd()
        try:
            os.chdir(repo_path)
            listing = list_repo_files()
            if not listing.get("success"):
                raise RuntimeError(listing.get("error", "Could not inspect repository."))
            paths = listing["files"]
            candidates: list[str] = []
            for signal in signals:
                if signal.file:
                    normalized = signal.file.replace("\\", "/").lstrip("./")
                    if normalized in paths:
                        candidates.append(normalized)
                    else:
                        basename = Path(normalized).name
                        candidates.extend(p for p in paths if Path(p).name == basename)
            if not candidates:
                candidates = [p for p in paths if Path(p).suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java"}][:8]
            source_files = {}
            for path in dict.fromkeys(candidates[:8]):
                result = read_repo_file({"path": path})
                if result.get("success"):
                    source_files[result["path"]] = result["content"]
        finally:
            os.chdir(old_cwd)

        if not source_files:
            raise ValueError("No safe repository source files were found for the failure.")
        provider = GeminiAdapter()
        proposal = generate_patch_proposal(provider, evidence, source_files)
        print("RepoPilot - CI Fix Proposal")
        print(f"Repository: {github_repo}\nRun ID: {args.run_id}")
        print("\nFailure summary:")
        for signal, analysis in zip(signals, analyses):
            print(f"- {signal.type}: {signal.message}; likely cause: {analysis.cause}")
        print(f"\nProposal: {proposal.summary}\n\nRationale:\n{proposal.rationale}")
        print("\nAffected files:\n" + "\n".join(f"- {path}" for path in proposal.files))
        print(f"\nUnified diff:\n{proposal.diff}\n\nRisks:\n{proposal.risks}")
        print("\nThis proposal is review-only; no files were modified.")
        return 0
    except ProposalValidationError as exc:
        print(f"RepoPilot proposal validation error: {exc}", file=sys.stderr)
        return 1
    except (GitHubAPIError, ValueError, RuntimeError, OSError) as exc:
        print(f"RepoPilot propose-fix error: {exc}", file=sys.stderr)
        return 1


def diagnose(argv: list[str]) -> int:
    """Diagnose a GitHub Actions run using deterministic analysis."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="repopilot diagnose",
        description=(
            "Diagnose a GitHub Actions workflow run using deterministic "
            "patterns and root-cause analysis."
        ),
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository in owner/repository format.",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        type=int,
        help="GitHub Actions workflow run ID.",
    )
    args = parser.parse_args(argv)

    if args.run_id <= 0:
        parser.error("--run-id must be a positive integer.")

    try:
        with GitHubClient() as client:
            run_info = client.get_run(args.repo, args.run_id)
            jobs = client.get_jobs(args.repo, args.run_id)

            print("\nRepoPilot - CI Failure Diagnosis")
            print("=" * 36)
            print(f"Repository: {args.repo}")
            print(f"Run ID:     {args.run_id}")
            print(f"Workflow:   {run_info.get('name', 'Unknown')}")
            print(f"Status:     {run_info.get('status', 'Unknown')}")
            print(
                f"Conclusion: {run_info.get('conclusion') or 'Pending'}"
            )

            failed_jobs = [
                job for job in jobs
                if job.get("conclusion") == "failure"
            ]

            if not failed_jobs:
                print("\nNo failed jobs were found in this run.")
                return 0

            print(f"\nFailed jobs: {len(failed_jobs)}")
            print(
                f"Inspecting up to {MAX_FAILED_JOBS_TO_INSPECT} "
                "failed jobs."
            )

            all_signals = 0

            for job in failed_jobs[:MAX_FAILED_JOBS_TO_INSPECT]:
                job_id = job.get("id")
                job_name = job.get("name", "Unknown job")

                print(f"\n--- Job: {job_name} (ID: {job_id}) ---")

                if (
                    isinstance(job_id, bool)
                    or not isinstance(job_id, int)
                    or job_id <= 0
                ):
                    print("Skipped: GitHub returned an invalid job ID.")
                    continue

                try:
                    logs = client.get_job_logs(args.repo, job_id)
                except GitHubAPIError as exc:
                    print(f"Could not retrieve job logs: {exc}")
                    continue

                signals = parse_log(logs)

                if not signals:
                    print("No recognized failure signatures found.")
                    continue

                all_signals += len(signals)

                for index, signal in enumerate(signals, start=1):
                    print(f"\nFailure {index}: {signal.type}")
                    print(f"  Message:    {signal.message}")
                    print(f"  Confidence: {signal.confidence:.0%}")

                    if signal.file:
                        location = signal.file
                        if signal.line is not None:
                            location += f":{signal.line}"
                        print(f"  Location:   {location}")

                    print("  Log excerpt:")
                    for line in signal.raw_excerpt.splitlines():
                        print(f"    {line}")

                    # RCA is read-only and uses the parsed signal.
                    analysis = analyze_signal(signal)

                    print("\n  Root-Cause Analysis:")
                    print(f"    Likely cause: {analysis.cause}")
                    print(
                        f"    Component:    "
                        f"{analysis.affected_component}"
                    )
                    print(
                        f"    Confidence:   "
                        f"{analysis.confidence:.0%}"
                    )
                    print(
                        f"    Next step:    "
                        f"{analysis.recommended_action}"
                    )

            print("\n" + "=" * 36)

            if all_signals:
                print(
                    f"Diagnosis complete: {all_signals} "
                    "signal(s) detected."
                )
            else:
                print(
                    "Diagnosis complete: no recognized failure "
                    "signatures were detected in the available logs."
                )

            print(
                "Analysis method: deterministic patterns and RCA "
                "(no LLM used for CI diagnosis)."
            )
            return 0

    except (GitHubAPIError, ValueError) as exc:
        print(f"RepoPilot diagnosis error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    """Preserve the existing RepoPilot agent CLI."""
    argv = sys.argv[1:]

    if argv and argv[0] == "diagnose":
        raise SystemExit(diagnose(argv[1:]))
    if argv and argv[0] == "propose-fix":
        raise SystemExit(propose_fix(argv[1:]))

    parser = argparse.ArgumentParser(
        description="RepoPilot: a measurable, human-controllable agent."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository directory (defaults to current directory).",
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Question to ask RepoPilot.",
    )

    args = parser.parse_args(argv)
    repo_path = args.repo.resolve()

    if not repo_path.is_dir():
        parser.error(f"Repository directory does not exist: {repo_path}")

    os.chdir(repo_path)

    question = " ".join(args.question).strip()
    if not question:
        question = "Check the current repository status and explain it."

    try:
        provider = GeminiAdapter()
        agent = Agent(provider=provider, max_steps=5)
        print("\nRepoPilot is investigating...\n")
        print(agent.run(question))
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f"RepoPilot error: {exc}\n")


if __name__ == "__main__":
    main()
