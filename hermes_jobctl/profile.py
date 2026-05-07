from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


def default_hermes_home() -> Path:
    return (Path.home() / ".hermes").resolve()


def infer_profile_from_cwd(cwd: Path | None = None) -> str | None:
    """Return Hermes named profile identifier, or None for default."""
    cw = (cwd or Path.cwd()).resolve()
    profiles_root = default_hermes_home() / "profiles"
    try:
        rel = cw.relative_to(profiles_root.resolve())
    except ValueError:
        return None
    if not rel.parts:
        return None
    return rel.parts[0]


def resolve_profile_explicit(
    profile_flag: str | None,
    env_profile: str | None,
    cwd: Path | None = None,
) -> str | None:
    """
    Resolution order:
    1. Typer/global --profile flag (non-empty string; 'default' => None).
    2. HERMES_JOBCTL_PROFILE env.
    3. infer_profile_from_cwd().
    """
    if profile_flag is not None:
        pf = profile_flag.strip()
        if not pf or pf.lower() == "default":
            return None
        return pf
    if env_profile:
        ev = env_profile.strip()
        if not ev or ev.lower() == "default":
            return None
        return ev
    return infer_profile_from_cwd(cwd)


def effective_hermes_home(profile_name: str | None) -> Path:
    base = default_hermes_home()
    if profile_name is None:
        return base
    return (base / "profiles" / profile_name).resolve()


@dataclass(frozen=True)
class CronInvoker:
    """Argv prefix ending with 'cron' (Hermes cron sub-parser)."""

    argv_prefix: tuple[str, ...]
    jobs_json_path: Path


def build_cron_context(
    profile_name: str | None,
    *,
    hermes_bin: str | None = None,
) -> CronInvoker:
    hb = shutil.which(str(hermes_bin or "").strip()) if hermes_bin and str(hermes_bin).strip() else None
    hermes = hb or shutil.which("hermes") or "hermes"
    hh = effective_hermes_home(profile_name)
    jobs = hh / "cron" / "jobs.json"

    if profile_name is None:
        prefix = (hermes, "cron")
        return CronInvoker(prefix, jobs)

    wrapper = shutil.which(profile_name)
    if wrapper:
        prefix = (profile_name, "cron")
        return CronInvoker(prefix, jobs)

    return CronInvoker((hermes, "-p", profile_name, "cron"), jobs)


def cron_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if extra:
        env.update(extra)
    return env
