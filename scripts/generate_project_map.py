#!/usr/bin/env python3
"""Generate a project map document from the repository structure."""

import json
import sys
from pathlib import Path


def generate_project_map(repo_root: Path) -> dict:
    """Scan repository for Python packages and entry points."""
    project_map: dict = {
        "name": repo_root.name,
        "description": f"Project map for {repo_root.name}",
        "modules": [],
        "entry_points": [],
    }

    seen_modules: set[str] = set()
    for py_file in sorted(repo_root.glob("**/__init__.py")):
        rel = py_file.relative_to(repo_root)
        parts = rel.parts[:-1]  # drop __init__.py
        if not parts:
            continue
        if "__pycache__" in parts or ".venv" in parts[0]:
            continue
        module_name = ".".join(parts)
        if module_name in seen_modules:
            continue
        seen_modules.add(module_name)
        project_map["modules"].append(
            {
                "name": module_name,
                "path": str(rel.parent),
                "description": f"Python package: {module_name}",
            }
        )

    for entry in ["main.py", "app.py", "api.py", "cli.py"]:
        if (repo_root / "agentManager" / entry).exists():
            project_map["entry_points"].append(f"agentManager/{entry}")
        elif (repo_root / entry).exists():
            project_map["entry_points"].append(entry)

    return project_map


def main() -> None:
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    project_map = generate_project_map(repo_root)

    output_dir = repo_root / "docs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "project-map.md"

    lines = [
        "# Project Map",
        "",
        f"**Project:** {project_map['name']}",
        "",
        "## Modules",
        "",
    ]
    for module in project_map["modules"]:
        lines.append(f"- **{module['name']}** (`{module['path']}`)")
    lines.append("")
    lines.append("## Entry Points")
    lines.append("")
    for ep in project_map["entry_points"]:
        lines.append(f"- `{ep}`")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {output_path}")


if __name__ == "__main__":
    main()
