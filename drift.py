from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .spec import TaskSpec


def _schedule_display(job: dict[str, Any]) -> str:
    sd = job.get("schedule_display")
    if isinstance(sd, str) and sd.strip():
        return sd.strip()
    sch = job.get("schedule")
    if isinstance(sch, str) and sch.strip():
        return sch.strip()
    if isinstance(sch, dict):
        try:
            return json.dumps(sch, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            pass
    return ""


def _normalize_deliver(job: dict[str, Any]) -> str | None:
    d = job.get("deliver")
    if d is None:
        return None
    if isinstance(d, str):
        return d.strip() or None
    if isinstance(d, list) and d:
        parts = [str(x).strip() for x in d if str(x).strip()]
        return ", ".join(parts) if parts else None
    return str(d).strip() or None


def _normalize_skills(job: dict[str, Any]) -> tuple[str, ...]:
    sk = job.get("skills")
    if sk is None and job.get("skill"):
        sk = [job["skill"]]
    if sk is None:
        return ()
    if isinstance(sk, str):
        sk = [sk]
    if not isinstance(sk, (list, tuple)):
        return ()
    out: list[str] = []
    for x in sk:
        t = str(x).strip()
        if t and t not in out:
            out.append(t)
    return tuple(out)


def _repeat_times(job: dict[str, Any]) -> int | None:
    r = job.get("repeat") or {}
    if not isinstance(r, dict):
        return None
    t = r.get("times")
    if t is None:
        return None
    try:
        return int(t)
    except (TypeError, ValueError):
        return None


def _normalize_script_workdir(job: dict[str, Any], key: str) -> str | None:
    v = job.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def job_is_paused(job: dict[str, Any]) -> bool:
    return str(job.get("state", "")) == "paused" or not bool(job.get("enabled", True))


@dataclass(frozen=True)
class DesiredState:
    schedule: str
    prompt: str
    deliver: str | None
    repeat: int | None
    skills: tuple[str, ...]
    script: str | None
    workdir: str | None
    suspend: bool


def desired_from_spec(spec: TaskSpec) -> DesiredState:
    return DesiredState(
        schedule=spec.schedule.strip(),
        prompt=spec.prompt_body,
        deliver=spec.deliver,
        repeat=spec.repeat,
        skills=spec.skills,
        script=spec.script,
        workdir=spec.workdir,
        suspend=spec.suspend,
    )


def drift_fields(desired: DesiredState, job: dict[str, Any]) -> list[str]:
    diffs: list[str] = []
    if desired.schedule != _schedule_display(job):
        diffs.append("schedule")
    jp = str(job.get("prompt") or "").strip()
    if desired.prompt != jp:
        diffs.append("prompt")
    jd = _normalize_deliver(job)
    if desired.deliver is not None and (desired.deliver or None) != (jd or None):
        diffs.append("deliver")
    jr = _repeat_times(job)
    if desired.repeat != jr:
        diffs.append("repeat")
    if desired.skills != _normalize_skills(job):
        diffs.append("skills")
    ws = _normalize_script_workdir(job, "script")
    ww = _normalize_script_workdir(job, "workdir")
    if (desired.script or None) != (ws or None):
        diffs.append("script")
    if (desired.workdir or None) != (ww or None):
        diffs.append("workdir")
    paused = job_is_paused(job)
    want_pause = desired.suspend
    if want_pause != paused:
        diffs.append("suspend")
    return diffs


def status_label(
    spec: TaskSpec,
    job: dict[str, Any] | None,
    ambiguous: bool,
) -> str:
    if ambiguous:
        return "ambiguous"
    if job is None:
        return "missing"
    d = desired_from_spec(spec)
    if drift_fields(d, job):
        return "pending_apply"
    return "sync"
