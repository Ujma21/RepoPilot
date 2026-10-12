
import argparse
import os
from pathlib import Path

from repopilot.core.agent import Agent
from repopilot.providers.gemini_adapter import GeminiAdapter


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RepoPilot: a measurable, human-controllable agent."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository directory to inspect (defaults to current directory).",
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Question to ask RepoPilot.",
    )

    args = parser.parse_args()
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