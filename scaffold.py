"""Scaffold new task spec Markdown files."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

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


def run_new(
    task_name: str,
    *,
    directory: Path | None,
    output: Path | None,
    schedule: str,
    force: bool,
    stdout_flag: bool,
) -> int:
    try:
        stem = validate_task_stem(task_name)
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

    text = render_spec_template(stem=stem_hint, schedule=schedule)

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