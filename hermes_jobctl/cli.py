from __future__ import annotations

import inspect
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Optional

import click
import typer
from typer.core import TyperGroup

from .commands import apply_paths, delete_targets, get_cmd, status_paths
from .scaffold import run_new


def _release_version() -> str:
    try:
        return version("hermes-jobctl")
    except PackageNotFoundError:
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if not pyproject.is_file():
            raise SystemExit(
                "hermes-jobctl: package is not installed and pyproject.toml was not found; "
                "install the project (e.g. uv sync) or run from a source checkout."
            ) from None
        in_project = False
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s == "[project]":
                in_project = True
                continue
            if in_project:
                if s.startswith("[") and s != "[project]":
                    break
                if s.startswith("version"):
                    _, _, rhs = s.partition("=")
                    val = rhs.strip().strip('"').strip("'")
                    if val:
                        return val
        raise SystemExit("hermes-jobctl: could not read version from pyproject.toml [project] table.") from None


class HermesTaskGroup(TyperGroup):
    """Render epilog like other help sections: heading flush left, body at one indent level (same as Commands)."""

    def format_epilog(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        if not self.epilog:
            return
        epilog = inspect.cleandoc(self.epilog)
        formatter.write_paragraph()
        formatter.write_heading("Spec format")
        with formatter.indentation():
            formatter.write_text(epilog)


# First line of the epilog paragraph must be ``\\b`` (ASCII 8) so Click's ``wrap_text`` treats the
# block as raw and keeps newlines (see click.formatting.wrap_text / ``preserve_paragraphs``).
# The "Spec format" title is emitted by :meth:`HermesTaskGroup.format_epilog` (same layout as ``Commands:``).
_TASK_SPEC_FIELDS_EPILOG = (
    "\x08\n"
    "Between the first --- and the closing ---, YAML; below that, Markdown is the Hermes prompt "
    "(never put the prompt in YAML).\n"
    "Field          Req?   Description\n"
    + "-" * 66
    + "\n"
    "type            yes    hermes-cron (only supported task kind today; reserved for extension)\n"
    "schedule       yes    hermes cron schedule (e.g. 30m, every 2h, 0 9 * * *)\n"
    "name           no     job name (default: .md filename without extension)\n"
    "deliver        no     maps to --deliver; omit for Hermes default\n"
    "repeat         no     integer; omit or <=0 → unlimited (Hermes rules)\n"
    "skills         no     list or one string → multiple --skill\n"
    "script         no     maps to --script\n"
    "workdir        no     maps to --workdir (Hermes rules; often absolute)\n"
    "suspend        no     bool; apply then pause/resume to match (default false)\n"
    "Any other YAML keys are ignored (not passed to Hermes)."
)

app = typer.Typer(
    cls=HermesTaskGroup,
    no_args_is_help=True,
    rich_markup_mode=None,
    help=(
        "Declarative Hermes cron tasks: each task is <task_name>.md "
        "with YAML front matter and a Markdown body (body = Hermes prompt). "
        "Example: examples/sample-cron-task.md"
    ),
    epilog=_TASK_SPEC_FIELDS_EPILOG,
)


@app.command()
def apply(
    paths: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            readable=True,
            help="Markdown task files and/or directories of *.md (non-recursive).",
        ),
    ],
    profile: Optional[str] = typer.Option(None, "--profile", "-p"),
    hermes_bin: Optional[str] = typer.Option(None, "--hermes-bin", envvar="HERMES_JOBCTL_HERMES_BIN"),
    accept_hooks: bool = typer.Option(False, "--accept-hooks"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Create or update Hermes cron jobs from task spec files.

    Front matter keys: see **Spec format** at the end of ``hermes-jobctl --help``.
    """
    code = apply_paths(paths, profile_opt=profile, hermes_bin=hermes_bin, accept_hooks=accept_hooks, verbose=verbose)
    raise typer.Exit(code)


@app.command()
def delete(
    paths: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            readable=True,
            help="Task .md and/or dirs of *.md (non-recursive). Omit when using --name.",
        ),
    ] = [],
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Effective task / job name."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p"),
    hermes_bin: Optional[str] = typer.Option(None, "--hermes-bin", envvar="HERMES_JOBCTL_HERMES_BIN"),
    accept_hooks: bool = typer.Option(False, "--accept-hooks"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Remove a Hermes cron job by spec file(s) / directory or by name."""
    try:
        code = delete_targets(
            paths,
            name,
            profile_opt=profile,
            hermes_bin=hermes_bin,
            accept_hooks=accept_hooks,
            verbose=verbose,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise typer.Exit(2) from e
    raise typer.Exit(code)


@app.command()
def status(
    paths: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            readable=True,
            help="Markdown task files and/or directories of *.md (non-recursive).",
        ),
    ],
    profile: Optional[str] = typer.Option(None, "--profile", "-p"),
    hermes_bin: Optional[str] = typer.Option(None, "--hermes-bin", envvar="HERMES_JOBCTL_HERMES_BIN"),
    json_out: bool = typer.Option(False, "--json", help="Print JSON rows."),
    show_diff: bool = typer.Option(False, "--show-diff", help="Extra hints when fields drift (use with -v)."),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero if any spec is invalid, missing job, drift, or ambiguous name.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Compare task files to jobs.json (sync / pending_apply / missing).

    Front matter keys: see **Spec format** at the end of ``hermes-jobctl --help``.
    """
    code = status_paths(
        paths,
        profile_opt=profile,
        hermes_bin=hermes_bin,
        json_out=json_out,
        show_diff=show_diff,
        strict=strict,
        verbose=verbose,
    )
    raise typer.Exit(code)


@app.command("get")
def get_jobs(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Filter by job name (exact)."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p"),
    hermes_bin: Optional[str] = typer.Option(None, "--hermes-bin", envvar="HERMES_JOBCTL_HERMES_BIN"),
    json_out: bool = typer.Option(False, "--json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """List jobs from jobs.json (optional name filter)."""
    code = get_cmd(
        name,
        profile_opt=profile,
        hermes_bin=hermes_bin,
        json_out=json_out,
        verbose=verbose,
    )
    raise typer.Exit(code)


@app.command()
def new(
    task_name: Annotated[
        Optional[str],
        typer.Argument(
            help="Base name for <name>.md (suffix .md allowed). Optional with --from-job.",
        ),
    ] = None,
    from_job: Optional[str] = typer.Option(
        None,
        "--from-job",
        help="Export spec from an existing Hermes cron job id (jobs.json).",
    ),
    directory: Optional[Path] = typer.Option(
        None,
        "--dir",
        help="Output directory (default: cwd). Mutually exclusive with --output.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path. Mutually exclusive with --dir.",
    ),
    schedule: Optional[str] = typer.Option(
        None,
        "--schedule",
        help="Initial schedule for blank template (default: every 24h). Not used with --from-job.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite if the file exists."),
    stdout_flag: bool = typer.Option(False, "--stdout", help="Print template to stdout; do not write a file."),
    profile: Optional[str] = typer.Option(None, "--profile", "-p"),
    hermes_bin: Optional[str] = typer.Option(None, "--hermes-bin", envvar="HERMES_JOBCTL_HERMES_BIN"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Scaffold a task spec with all supported YAML keys (optional ones commented out)."""
    code = run_new(
        task_name,
        from_job_id=from_job,
        profile_opt=profile,
        hermes_bin=hermes_bin,
        verbose=verbose,
        directory=directory,
        output=output,
        schedule=schedule,
        force=force,
        stdout_flag=stdout_flag,
    )
    raise typer.Exit(code)


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] in ("--version", "-V"):
        print(f"hermes-jobctl {_release_version()}")
        raise SystemExit(0)
    app()


if __name__ == "__main__":
    main()
