"""Scaffold new task spec Markdown files."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .drift import job_fields_for_spec
from .state import find_job_by_id, load_all_jobs

_STEM_DISALLOWED = re.compile(r"[/\0\n\r\t\x00-\x1f]")

_DEFAULT_SCHEDULE = "every 24h"


def normalize_task_stem_argument(name: str) -> str:
    """Allow ``task_name`` or ``task_name.md``."""
    s = name.strip()
    low = s.lower()
    if low.endswith(".md"):
        s = s[:-3]
    return s.strip()


def validate_task_stem(name: str) -> str:
    stem = normalize_task_stem_argument(name)
    if not stem:
        raise ValueError("Task name must be non-empty.")
    if stem in (".", ".."):
        raise ValueError(f"Invalid task name: {name!r}")
    if _STEM_DISALLOWED.search(stem):
        raise ValueError(
            f"Task name must not contain path separators or control characters: {name!r}"
        )
    return stem


def stem_from_job_name(name: str) -> str:
    """Derive a safe file stem from a Hermes job name."""
    raw = str(name or "").strip()
    if not raw:
        raise ValueError("Job has no name; provide TASK or use --output.")
    stem = _STEM_DISALLOWED.sub("_", raw)
    stem = re.sub(r"_+", "_", stem).strip("_")
    if not stem or stem in (".", ".."):
        raise ValueError(
            f"Job name {name!r} cannot be used as a file name; provide TASK or use --output."
        )
    return stem


def resolve_new_output_path(
    stem: str,
    *,
    directory: Path | None,
    output: Path | None,
) -> Path:
    if output is not None:
        return output.expanduser().resolve()
    base = Path(directory or Path.cwd()).expanduser().resolve()
    return (base / f"{stem}.md").resolve()


def render_spec_template(*, stem: str, schedule: str) -> str:
    sch = schedule.strip() or _DEFAULT_SCHEDULE
    quoted = json.dumps(sch)
    return f"""---
type: hermes-cron
schedule: {quoted}
# Optional — uncomment as needed (default job name is this file stem {stem!r})
# name: override-job-name
# deliver: local
# repeat: 10
# skills:
#   - my-skill
# script: /path/under/hermes/scripts/prep.py
# workdir: /absolute/path/to/project
# suspend: false
---
Write the agent prompt below (Markdown body; not YAML).

- …
"""


def _yaml_line(key: str, value: str | int | bool) -> str:
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    elif isinstance(value, int):
        rendered = str(value)
    elif key == "type":
        rendered = str(value)
    else:
        rendered = json.dumps(value)
    return f"{key}: {rendered}"


def render_spec_from_job(job: dict, *, stem: str) -> str:
    fields = job_fields_for_spec(job)
    if not fields.schedule:
        raise ValueError("Job has no schedule; cannot scaffold spec.")
    if not fields.prompt:
        jid = str(job.get("id", "?"))
        raise ValueError(f"Job {jid} has empty prompt; cannot scaffold spec.")

    lines: list[str] = ["---", _yaml_line("type", "hermes-cron"), _yaml_line("schedule", fields.schedule)]
    if fields.job_name and fields.job_name != stem:
        lines.append(_yaml_line("name", fields.job_name))
    if fields.deliver:
        lines.append(_yaml_line("deliver", fields.deliver))
    if fields.repeat is not None:
        lines.append(_yaml_line("repeat", fields.repeat))
    if fields.skills:
        lines.append("skills:")
        for sk in fields.skills:
            lines.append(f"  - {json.dumps(sk)}")
    if fields.script:
        lines.append(_yaml_line("script", fields.script))
    if fields.workdir:
        lines.append(_yaml_line("workdir", fields.workdir))
    if fields.suspend:
        lines.append(_yaml_line("suspend", True))
    lines.append("---")
    return "\n".join(lines) + "\n" + fields.prompt + "\n"


def run_new(
    task_name: str | None,
    *,
    from_job_id: str | None,
    profile_opt: str | None,
    hermes_bin: str | None,
    verbose: bool,
    directory: Path | None,
    output: Path | None,
    schedule: str | None,
    force: bool,
    stdout_flag: bool,
) -> int:
    if from_job_id and schedule is not None:
        print("error: --from-job cannot be used with --schedule", file=sys.stderr)
        return 2

    job: dict | None = None
    if from_job_id:
        from .commands import resolve_invoker

        _, invoker = resolve_invoker(profile_opt, hermes_bin)
        if verbose:
            print(f"jobs.json: {invoker.jobs_json_path}", file=sys.stderr)
        try:
            jobs = load_all_jobs(invoker.jobs_json_path)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        job = find_job_by_id(jobs, from_job_id)
        if job is None:
            print(f"error: job not found: {from_job_id}", file=sys.stderr)
            return 1

    if job is None and not task_name:
        print("error: TASK name required", file=sys.stderr)
        return 2

    try:
        if job is not None:
            if task_name:
                stem = validate_task_stem(task_name)
            else:
                stem = stem_from_job_name(str(job.get("name") or ""))
        else:
            stem = validate_task_stem(task_name or "")
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if directory is not None and output is not None:
        print("error: use only one of --dir and --output", file=sys.stderr)
        return 2

    out_path = resolve_new_output_path(stem, directory=directory, output=output)
    stem_hint = stem if stdout_flag else out_path.stem
    if not stem_hint or stem_hint in (".", ".."):
        print("error: invalid output path stem", file=sys.stderr)
        return 2

    if job is not None:
        try:
            text = render_spec_from_job(job, stem=stem_hint)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    else:
        sch = (schedule or "").strip() or _DEFAULT_SCHEDULE
        text = render_spec_template(stem=stem_hint, schedule=sch)

    if stdout_flag:
        if directory is not None or output is not None:
            print("error: --stdout conflicts with --dir / --output", file=sys.stderr)
            return 2
        sys.stdout.write(text)
        return 0

    if out_path.exists() and not force:
        print(f"error: file exists: {out_path} (--force to overwrite)", file=sys.stderr)
        return 1
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(out_path)
    return 0
