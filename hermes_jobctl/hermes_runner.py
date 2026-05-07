from __future__ import annotations

import os
import subprocess
from typing import Sequence

from .profile import CronInvoker


class HermesCliError(RuntimeError):
    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def run_cron(
    invoker: CronInvoker,
    cron_args: Sequence[str],
    *,
    accept_hooks: bool = False,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    cmd = list(invoker.argv_prefix)
    if accept_hooks:
        cmd.append("--accept-hooks")
    cmd.extend(list(cron_args))
    env = os.environ.copy()
    if accept_hooks:
        env.setdefault("HERMES_ACCEPT_HOOKS", "1")
    kw: dict = {"env": env, "text": True}
    if capture:
        kw["capture_output"] = True
    try:
        return subprocess.run(cmd, check=False, **kw)  # type: ignore[arg-type]
    except OSError as e:
        raise HermesCliError(f"Failed to run {cmd[0]!r}: {e}") from e


def build_create_args(spec) -> list[str]:
    from .spec import TaskSpec

    if not isinstance(spec, TaskSpec):
        raise TypeError("TaskSpec expected")
    args: list[str] = ["create", spec.schedule, spec.prompt_for_hermes()]
    args.extend(["--name", spec.effective_name])
    if spec.deliver:
        args.extend(["--deliver", spec.deliver])
    if spec.repeat is not None:
        args.extend(["--repeat", str(spec.repeat)])
    for s in spec.skills:
        args.extend(["--skill", s])
    if spec.script:
        args.extend(["--script", spec.script])
    if spec.workdir:
        args.extend(["--workdir", spec.workdir])
    return args


def build_edit_args(job_id: str, spec) -> list[str]:
    """Full replacement edit so spec matches Hermes job (declarative sync)."""
    from .spec import TaskSpec

    if not isinstance(spec, TaskSpec):
        raise TypeError("TaskSpec expected")
    args: list[str] = [
        "edit",
        job_id,
        "--schedule",
        spec.schedule,
        "--prompt",
        spec.prompt_for_hermes(),
        "--name",
        spec.effective_name,
    ]
    # Always pass deliver; empty clears (Hermes update path).
    args.extend(["--deliver", spec.deliver if spec.deliver else ""])
    # repeat: 0 => infinite per Hermes tool update branch
    args.extend(["--repeat", str(spec.repeat if spec.repeat is not None else 0)])

    if spec.skills:
        for s in spec.skills:
            args.extend(["--skill", s])
    else:
        args.append("--clear-skills")

    args.extend(["--script", spec.script if spec.script else ""])
    args.extend(["--workdir", spec.workdir if spec.workdir else ""])
    return args


def build_remove_args(job_id: str) -> list[str]:
    return ["remove", job_id]


def build_pause_args(job_id: str) -> list[str]:
    return ["pause", job_id]


def build_resume_args(job_id: str) -> list[str]:
    return ["resume", job_id]


def check_ok(proc: subprocess.CompletedProcess[str], cmd_hint: str) -> None:
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise HermesCliError(
            f"{cmd_hint} failed (exit {proc.returncode}): {err or 'no output'}",
            returncode=proc.returncode,
            stderr=err,
        )
