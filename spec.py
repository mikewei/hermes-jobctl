from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml


class TaskSpecError(ValueError):
    pass


# YAML front matter key `type`; values reserved for future task kinds.
TASK_TYPE_HERMES_CRON = "hermes-cron"
ALLOWED_TASK_TYPES = frozenset({TASK_TYPE_HERMES_CRON})


@dataclass(frozen=True)
class TaskSpec:
    path: Path
    task_type: str  # from front matter key `type`
    effective_name: str
    schedule: str
    deliver: str | None
    repeat: int | None
    skills: tuple[str, ...]
    script: str | None
    workdir: str | None
    suspend: bool
    prompt_body: str  # stripped, used as Hermes prompt

    def prompt_for_hermes(self) -> str:
        return self.prompt_body


def _parse_bool(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "1", "on"):
            return True
        if s in ("false", "no", "0", "off", ""):
            return False
    raise TaskSpecError(f"Invalid boolean value: {v!r}")


def _skills_from_meta(meta: dict[str, Any]) -> tuple[str, ...]:
    raw = meta.get("skills")
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raise TaskSpecError("`skills` must be a list of strings")
    out: list[str] = []
    for x in raw:
        t = str(x).strip()
        if t:
            out.append(t)
    return tuple(out)


def split_front_matter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        raise TaskSpecError("Task file must start with YAML front matter (---)")
    # First line is --- ; find closing ---
    tail = text[3:]  # after first ---
    if tail.startswith("\n"):
        tail = tail[1:]
    close_idx = tail.find("\n---")
    if close_idx < 0:
        raise TaskSpecError("Missing closing --- for YAML front matter")
    header = tail[:close_idx].strip("\n")
    rest = tail[close_idx + 4 :]  # after \n---
    return header, rest


def parse_task_file(path: Path) -> TaskSpec:
    raw = Path(path).read_text(encoding="utf-8")
    return parse_task_text(path.resolve(), raw)


def parse_task_text(path: Path, content: str) -> TaskSpec:
    header, body_rest = split_front_matter(content)
    try:
        meta = yaml.safe_load(header) or {}
    except yaml.YAMLError as e:
        raise TaskSpecError(f"Invalid YAML front matter: {e}") from e
    if not isinstance(meta, dict):
        raise TaskSpecError("Front matter must be a YAML mapping")

    type_raw = meta.get("type")
    if type_raw is None or not str(type_raw).strip():
        raise TaskSpecError(
            "`type` is required in front matter "
            f"(known values: {', '.join(sorted(ALLOWED_TASK_TYPES))})"
        )
    task_type = str(type_raw).strip()
    if task_type not in ALLOWED_TASK_TYPES:
        raise TaskSpecError(
            f"`type` must be one of: {', '.join(sorted(ALLOWED_TASK_TYPES))} (got {task_type!r})"
        )

    schedule_raw = meta.get("schedule")
    if schedule_raw is None or not str(schedule_raw).strip():
        raise TaskSpecError("`schedule` is required in front matter")
    schedule = str(schedule_raw).strip()

    stem = Path(path).stem
    effective = meta.get("name")
    effective_name = (
        str(effective).strip() if effective not in (None, "") else str(stem).strip()
    )
    if not effective_name:
        raise TaskSpecError("Derived task name is empty (set front matter name or use a valid file name)")

    deliver_raw = meta.get("deliver")
    deliver = str(deliver_raw).strip() if deliver_raw not in (None, "") else None

    repeat = meta.get("repeat")
    repeat_i: int | None
    if repeat is None:
        repeat_i = None
    else:
        try:
            repeat_i = int(repeat)
        except (TypeError, ValueError) as e:
            raise TaskSpecError("`repeat` must be an integer") from e
        if repeat_i <= 0:
            repeat_i = None

    script_raw = meta.get("script")
    script = str(script_raw).strip() if script_raw not in (None, "") else None
    wd_raw = meta.get("workdir")
    workdir = str(wd_raw).strip() if wd_raw not in (None, "") else None

    skills = _skills_from_meta(meta)
    suspend = _parse_bool(meta.get("suspend"), default=False)

    prompt_body = body_rest.strip()
    if not prompt_body:
        raise TaskSpecError("Prompt body (Markdown after front matter) must be non-empty")

    return TaskSpec(
        path=path,
        task_type=task_type,
        effective_name=effective_name,
        schedule=schedule,
        deliver=deliver,
        repeat=repeat_i,
        skills=skills,
        script=script,
        workdir=workdir,
        suspend=suspend,
        prompt_body=prompt_body,
    )


def iter_task_markdown_files(target: Path) -> Iterator[Path]:
    p = target.resolve()
    if p.is_file():
        if p.suffix.lower() != ".md":
            raise TaskSpecError(f"Not a Markdown file: {p}")
        yield p
        return
    if not p.is_dir():
        raise TaskSpecError(f"Not a file or directory: {p}")
    files = sorted(p.glob("*.md"))
    for f in files:
        if f.is_file():
            yield f
