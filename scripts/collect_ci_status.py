"""Generate a CI-backed verification summary.

The script is intentionally dependency-free so it can run even when project
dependency installation fails. GitHub Actions metadata is read from environment
variables; local runs report missing CI values as explicit unknowns.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


UNKNOWN = "unknown (not running in GitHub Actions)"


@dataclass(frozen=True)
class CommandResult:
    command: str
    status: str
    details: str


def normalize_status(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "success": "pass",
        "passed": "pass",
        "pass": "pass",
        "failure": "fail",
        "failed": "fail",
        "fail": "fail",
        "cancelled": "fail",
        "timed_out": "fail",
        "skipped": "skipped",
        "skip": "skipped",
        "": "unknown",
        "unknown": "unknown",
    }
    return aliases.get(normalized, "unknown")


def parse_command_result(raw: str) -> CommandResult:
    parts = raw.split("::", 2)
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            "--command-result must use 'status::command::details' format"
        )

    status, command, details = parts
    command = command.strip()
    details = details.strip()
    if not command:
        raise argparse.ArgumentTypeError("command cannot be empty")

    return CommandResult(
        command=command,
        status=normalize_status(status),
        details=details or "-",
    )


def env_value(name: str) -> str:
    return os.environ.get(name) or UNKNOWN


def ci_run_url(repository: str, run_id: str) -> str:
    if repository == UNKNOWN or run_id == UNKNOWN:
        return UNKNOWN
    return f"https://github.com/{repository}/actions/runs/{run_id}"


def markdown_table_row(values: list[str]) -> str:
    escaped = [value.replace("|", "\\|").replace("\n", " ") for value in values]
    return "| " + " | ".join(escaped) + " |"


def render_summary(
    *,
    python_version: str,
    commands: list[CommandResult],
    known_blockers: list[str],
) -> str:
    repository = env_value("GITHUB_REPOSITORY")
    run_id = env_value("GITHUB_RUN_ID")
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    lines = [
        "# Verification Summary",
        "",
        "## CI Metadata",
        "",
        markdown_table_row(["Field", "Value"]),
        markdown_table_row(["---", "---"]),
        markdown_table_row(["Generated at", generated_at]),
        markdown_table_row(["Commit SHA", env_value("GITHUB_SHA")]),
        markdown_table_row(["Branch", env_value("GITHUB_REF_NAME")]),
        markdown_table_row(["Repository", repository]),
        markdown_table_row(["GitHub run ID", run_id]),
        markdown_table_row(["CI run URL", ci_run_url(repository, run_id)]),
        markdown_table_row(["Runner OS", env_value("RUNNER_OS")]),
        markdown_table_row(["Python version", python_version]),
        "",
        "## Commands",
        "",
        markdown_table_row(["Status", "Command", "Details"]),
        markdown_table_row(["---", "---", "---"]),
    ]

    if commands:
        for command in commands:
            lines.append(
                markdown_table_row([command.status, command.command, command.details])
            )
    else:
        lines.append(markdown_table_row(["unknown", "No commands provided", "-"]))

    lines.extend(["", "## Known Blockers", ""])
    if known_blockers:
        lines.extend(f"- {blocker}" for blocker in known_blockers)
    else:
        lines.append("- No known blockers reported.")

    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown verification summary from CI metadata."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the Markdown verification summary.",
    )
    parser.add_argument(
        "--python-version",
        default=sys.version.split()[0],
        help="Python version used for verification. Defaults to current interpreter.",
    )
    parser.add_argument(
        "--command-result",
        action="append",
        default=[],
        type=parse_command_result,
        metavar="STATUS::COMMAND::DETAILS",
        help="Command result to include. Repeat for multiple commands.",
    )
    parser.add_argument(
        "--known-blocker",
        action="append",
        default=[],
        help="Known blocker to list in the summary. Repeat for multiple blockers.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_summary(
            python_version=args.python_version,
            commands=args.command_result,
            known_blockers=args.known_blocker,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
