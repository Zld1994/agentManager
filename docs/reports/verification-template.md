# Verification Report Template

Use this template for completion reports and release notes that make verification
claims. Prefer CI-backed evidence. If verification is local-only, mark it
clearly and include the reason CI evidence is unavailable.

## Metadata

| Field | Value |
| --- | --- |
| Commit SHA | `<commit-sha>` |
| Branch | `<branch-name>` |
| Python version | `<python-version>` |
| CI run URL | `<github-actions-run-url-or-local-only>` |
| Verification mode | `CI-backed` / `local-only` |

## Commands

| Status | Command | Notes |
| --- | --- | --- |
| pass/fail/skipped | `<command>` | `<short result or reason>` |

## Known Blockers

- `<blocker, environment constraint, or skipped verification reason>`

## Completion Statement

`<State exactly what was verified. Do not claim full-suite or production readiness
unless the CI run or listed commands prove it.>`
