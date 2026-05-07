from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_all_jobs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid jobs.json at {path}: {e}") from e
    if isinstance(data, list):
        return list(data)
    if isinstance(data, dict) and isinstance(data.get("jobs"), list):
        return list(data["jobs"])
    if isinstance(data, dict) and data == {}:
        return []
    if isinstance(data, dict):
        # Older / hand-edited files may be {}; tolerate unknown dict as empty store.
        j = data.get("jobs")
        if isinstance(j, list):
            return list(j)
        return []
    raise ValueError(f"jobs.json must be a JSON list at {path}")


def find_jobs_by_name(jobs: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [j for j in jobs if isinstance(j, dict) and str(j.get("name", "")) == name]


def singleton_job_or_error(jobs: list[dict[str, Any]], name: str) -> tuple[dict[str, Any] | None, str | None]:
    """
    Returns (job, error_message). If multiple matches, error_message is set.
    """
    m = find_jobs_by_name(jobs, name)
    if len(m) == 0:
        return None, None
    if len(m) > 1:
        ids = ", ".join(str(j.get("id", "?")) for j in m)
        return None, f"multiple jobs named {name!r}: {ids}"
    return m[0], None
