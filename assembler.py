import json
import os
import re
from datetime import datetime, timezone

from orchestrator import FileSpec, TaskResult, TaskSpec


def get_comment_char(file_path: str) -> str:
    """Return the single-line comment prefix for a file based on its extension."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".js", ".ts", ".rs", ".go", ".java", ".c", ".cpp", ".cs", ".swift", ".kt"):
        return "//"
    return "#"


def replace_placeholders(
    skeleton: str, results: dict[str, TaskResult], file_path: str
) -> tuple[str, dict[str, tuple[int, int]]]:
    """Replace <<TASK_ID: desc>> placeholders with microagent code.

    Returns the assembled code and a dict mapping task_id -> (line_start, line_end).
    """
    lines = skeleton.split("\n")
    output_lines = []
    line_map = {}

    placeholder_re = re.compile(r"^(\s*)<<(\w+):\s*(.+?)>>\s*$")
    followup_re = re.compile(r"^\s*(?:#|//)\s*(?:Task|Inputs|Outputs|Context):")

    i = 0
    while i < len(lines):
        match = placeholder_re.match(lines[i])
        if match:
            indent = match.group(1)
            task_id = match.group(2)
            description = match.group(3)

            # Skip the placeholder line
            i += 1
            # Skip follow-up comment lines (# Task:, # Inputs:, etc.)
            while i < len(lines) and followup_re.match(lines[i]):
                i += 1

            # Insert replacement code
            start_line = len(output_lines) + 1  # 1-indexed
            result = results.get(task_id)

            if result and result.status == "ok":
                code_lines = result.code.rstrip("\n").split("\n")
                for code_line in code_lines:
                    if code_line.strip():
                        output_lines.append(indent + code_line)
                    else:
                        output_lines.append("")
            else:
                error_msg = result.error if result else "no result received"
                comment = get_comment_char(file_path)
                output_lines.append(
                    f"{indent}{comment} <<{task_id}: {description}>> -- FAILED: {error_msg}"
                )

            end_line = len(output_lines)
            line_map[task_id] = (start_line, end_line)
        else:
            output_lines.append(lines[i])
            i += 1

    return "\n".join(output_lines), line_map


def slugify(description: str) -> str:
    """Convert a project description to a filesystem-safe directory name."""
    slug = description.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug[:50]


def _detect_setup_command(file_paths: list[str]) -> tuple[str, str]:
    """Infer setup and run commands from generated file paths."""
    names = {os.path.basename(p) for p in file_paths}

    if "requirements.txt" in names:
        return "pip install -r requirements.txt", "python main.py"
    if "package.json" in names:
        return "npm install", "npm start"
    if "Cargo.toml" in names:
        return "cargo build", "cargo run"

    # Detect by extension
    extensions = {os.path.splitext(p)[1] for p in file_paths}
    if ".py" in extensions:
        return "pip install -r requirements.txt", "python main.py"
    if ".ts" in extensions or ".js" in extensions:
        return "npm install", "npm start"
    if ".rs" in extensions:
        return "cargo build", "cargo run"

    return "(see files for setup instructions)", "(see files for usage)"


def write_build_report(
    output_dir: str,
    description: str,
    config: dict,
    file_specs: list[FileSpec],
    task_specs: list[TaskSpec],
    results: dict[str, TaskResult],
    all_line_maps: dict[str, dict[str, tuple[int, int]]],
    log_file: str,
) -> None:
    """Write build_report.json to the output directory."""
    task_spec_map = {ts.task_id: ts for ts in task_specs}

    tasks_report = []
    for fs in file_specs:
        line_map = all_line_maps.get(fs.path, {})
        for tid in fs.task_ids:
            spec = task_spec_map.get(tid)
            result = results.get(tid)
            tasks_report.append(
                {
                    "task_id": tid,
                    "file": fs.path,
                    "line_start": line_map.get(tid, (0, 0))[0],
                    "line_end": line_map.get(tid, (0, 0))[1],
                    "instruction": spec.instruction if spec else "",
                    "status": result.status if result else "failed",
                    "error": result.error if result else "no result",
                }
            )

    succeeded = sum(1 for r in results.values() if r.status == "ok")
    failed = sum(1 for r in results.values() if r.status == "failed")

    report = {
        "project_description": description,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "orchestrator_model": config["orchestrator"]["model"],
        "microagent_model": config["microagent"]["model"],
        "files": [{"path": fs.path, "tasks": fs.task_ids} for fs in file_specs],
        "tasks": tasks_report,
        "summary": {
            "total_files": len(file_specs),
            "total_tasks": len(results),
            "succeeded": succeeded,
            "failed": failed,
        },
        "log_file": log_file,
    }

    path = os.path.join(output_dir, "build_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)


def write_readme(
    output_dir: str,
    description: str,
    file_specs: list[FileSpec],
    results: dict[str, TaskResult],
) -> None:
    """Write a README.md for the generated project."""
    file_paths = [fs.path for fs in file_specs]
    setup_cmd, run_cmd = _detect_setup_command(file_paths)

    succeeded = sum(1 for r in results.values() if r.status == "ok")
    total = len(results)

    # Derive project name from description
    words = description.split()[:6]
    project_name = " ".join(w.capitalize() for w in words)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    readme = f"""# {project_name}

{description}

## Setup

```
{setup_cmd}
```

## Usage

```
{run_cmd}
```

## Build Info

Generated by Microagents.
- Generated: {timestamp}
- Tasks: {succeeded} / {total}

See build_report.json for task-to-line mappings.
"""

    path = os.path.join(output_dir, "README.md")
    with open(path, "w") as f:
        f.write(readme)


def assemble_project(
    file_specs: list[FileSpec],
    results: dict[str, TaskResult],
    task_specs: list[TaskSpec],
    description: str,
    config: dict,
    log_file: str,
) -> str:
    """Assemble all output files, build report, and README. Returns output path."""
    project_name = slugify(description)
    output_dir = os.path.join(config["output"]["dir"], project_name)
    os.makedirs(output_dir, exist_ok=True)

    all_line_maps: dict[str, dict[str, tuple[int, int]]] = {}

    for fs in file_specs:
        assembled, line_map = replace_placeholders(fs.skeleton, results, fs.path)
        all_line_maps[fs.path] = line_map

        file_path = os.path.join(output_dir, fs.path)
        file_dir = os.path.dirname(file_path)
        if file_dir:
            os.makedirs(file_dir, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(assembled)

    write_build_report(
        output_dir, description, config, file_specs, task_specs, results, all_line_maps, log_file
    )
    write_readme(output_dir, description, file_specs, results)

    return output_dir
