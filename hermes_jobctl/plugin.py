"""Hermes plugin entrypoint for `hermes jobctl ...`.

Supports both:
- Python entry-point loading (`hermes_agent.plugins`)
- Directory plugin loading when this package is copied under Hermes plugins.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# When plugin.py is executed as a top-level module (directory plugin loaders),
# make sure relative imports still work by setting package context.
if __package__ in (None, ""):
    _pkg_dir = Path(__file__).resolve().parent
    _parent = str(_pkg_dir.parent)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    __package__ = _pkg_dir.name

from .commands import apply_paths, delete_targets, get_cmd, status_paths
from .scaffold import run_new

__all__ = ["register", "setup_argparse", "handle_cli"]


def register(ctx) -> None:
    """Wire the plugin into Hermes' CLI command registry."""
    ctx.register_cli_command(
        name="jobctl",
        help="Manage hermes-jobctl markdown task specs (apply/status/delete/get/new)",
        setup_fn=setup_argparse,
        handler_fn=handle_cli,
    )


def _profile_from_hermes_home() -> str | None:
    """Map Hermes ``HERMES_HOME`` to a hermes-jobctl profile name."""
    raw = os.environ.get("HERMES_HOME")
    if not raw:
        return None
    try:
        hh = Path(raw).expanduser().resolve()
    except OSError:
        return None
    default_root = (Path.home() / ".hermes").resolve()
    if hh == default_root:
        return None
    profiles_root = default_root / "profiles"
    try:
        rel = hh.relative_to(profiles_root)
    except ValueError:
        print(
            f"jobctl: HERMES_HOME={raw} is outside {profiles_root}; "
            "falling back to default profile resolution.",
            file=sys.stderr,
        )
        return None
    return rel.parts[0] if rel.parts else None


def _resolve_profile(args_profile: str | None) -> str | None:
    """Resolve effective profile name for plugin invocations."""
    if args_profile:
        return args_profile
    env_profile = os.environ.get("HERMES_JOBCTL_PROFILE")
    if env_profile and env_profile.strip():
        return env_profile.strip()
    return _profile_from_hermes_home()


def _add_common_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("-p", "--profile", default=None, help="Hermes profile name (overrides auto-detection)")
    p.add_argument("--hermes-bin", default=None, help="Path to the hermes binary")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose output")


def setup_argparse(subparser: argparse.ArgumentParser) -> None:
    """Build the argparse tree under ``hermes jobctl``."""
    subs = subparser.add_subparsers(dest="hj_subcommand", metavar="<command>")

    p_apply = subs.add_parser("apply", help="Create or update jobs from task specs")
    p_apply.add_argument("paths", nargs="+", type=Path, help="Markdown task file(s) or directories of *.md")
    p_apply.add_argument("--accept-hooks", action="store_true")
    _add_common_flags(p_apply)

    p_status = subs.add_parser("status", help="Compare task files to jobs.json")
    p_status.add_argument("paths", nargs="+", type=Path, help="Markdown task file(s) or directories of *.md")
    p_status.add_argument("--json", dest="json_out", action="store_true", help="Print JSON rows")
    p_status.add_argument("--show-diff", action="store_true", help="Extra hints when fields drift (use with -v)")
    p_status.add_argument("--strict", action="store_true", help="Exit non-zero on missing/drift/ambiguous")
    _add_common_flags(p_status)

    p_delete = subs.add_parser("delete", help="Remove jobs by spec path(s) or by name")
    p_delete.add_argument("paths", nargs="*", type=Path, help="Task .md / directories (omit when using --name)")
    p_delete.add_argument("-n", "--name", default=None, help="Effective task / job name")
    p_delete.add_argument("--accept-hooks", action="store_true")
    _add_common_flags(p_delete)

    p_get = subs.add_parser("get", help="List jobs from jobs.json")
    p_get.add_argument("-n", "--name", default=None, help="Filter by job name (exact)")
    p_get.add_argument("--json", dest="json_out", action="store_true", help="Print JSON")
    _add_common_flags(p_get)

    p_new = subs.add_parser("new", help="Scaffold a task spec markdown file")
    p_new.add_argument(
        "task_name",
        nargs="?",
        default=None,
        help="Base name for <task>.md (suffix .md allowed; optional with --from-job)",
    )
    p_new.add_argument("--from-job", dest="from_job_id", default=None, help="Export from existing job id")
    p_new.add_argument("--dir", dest="directory", type=Path, default=None, help="Output directory (default cwd)")
    p_new.add_argument("-o", "--output", type=Path, default=None, help="Output file path")
    p_new.add_argument(
        "--schedule",
        default=None,
        help="Initial schedule for blank template (default every 24h; not used with --from-job)",
    )
    p_new.add_argument("--force", action="store_true", help="Overwrite if the file exists")
    p_new.add_argument("--stdout", dest="stdout_flag", action="store_true", help="Print template; do not write")
    _add_common_flags(p_new)

    subparser.set_defaults(func=handle_cli)


def handle_cli(args: argparse.Namespace) -> int:
    """Dispatch parsed args to the underlying hermes_jobctl business functions."""
    sub = getattr(args, "hj_subcommand", None)
    if sub is None:
        print("Usage: hermes jobctl <apply|status|delete|get|new> [...]", file=sys.stderr)
        return 2

    if sub == "new":
        return run_new(
            args.task_name,
            from_job_id=getattr(args, "from_job_id", None),
            profile_opt=_resolve_profile(getattr(args, "profile", None)),
            hermes_bin=getattr(args, "hermes_bin", None),
            verbose=bool(getattr(args, "verbose", False)),
            directory=args.directory,
            output=args.output,
            schedule=args.schedule,
            force=args.force,
            stdout_flag=args.stdout_flag,
        )

    profile_opt = _resolve_profile(getattr(args, "profile", None))
    hermes_bin = getattr(args, "hermes_bin", None)
    verbose = bool(getattr(args, "verbose", False))

    if sub == "apply":
        return apply_paths(
            list(args.paths),
            profile_opt=profile_opt,
            hermes_bin=hermes_bin,
            accept_hooks=bool(args.accept_hooks),
            verbose=verbose,
        )

    if sub == "status":
        return status_paths(
            list(args.paths),
            profile_opt=profile_opt,
            hermes_bin=hermes_bin,
            json_out=bool(args.json_out),
            show_diff=bool(args.show_diff),
            strict=bool(args.strict),
            verbose=verbose,
        )

    if sub == "delete":
        try:
            return delete_targets(
                list(args.paths or []),
                args.name,
                profile_opt=profile_opt,
                hermes_bin=hermes_bin,
                accept_hooks=bool(args.accept_hooks),
                verbose=verbose,
            )
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

    if sub == "get":
        return get_cmd(
            args.name,
            profile_opt=profile_opt,
            hermes_bin=hermes_bin,
            json_out=bool(args.json_out),
            verbose=verbose,
        )

    print(f"jobctl: unknown subcommand {sub!r}", file=sys.stderr)
    return 2
