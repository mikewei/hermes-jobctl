from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .drift import desired_from_spec, drift_fields, job_is_paused, status_label
from .hermes_runner import (
    HermesCliError,
    build_create_args,
    build_edit_args,
    build_pause_args,
    build_remove_args,
    build_resume_args,
    check_ok,
    run_cron,
)
from .profile import CronInvoker, build_cron_context, default_hermes_home, resolve_profile_explicit
from .spec import TaskSpecError, iter_task_markdown_files, parse_task_file
from .state import find_jobs_by_name, load_all_jobs, singleton_job_or_error


class OpError(Exception):
    def __init__(self, msg: str, path: Path | None = None):
        super().__init__(msg)
        self.path = path


def resolve_invoker(
    profile_opt: str | None,
    hermes_bin: str | None,
) -> tuple[str | None, CronInvoker]:
    p = resolve_profile_explicit(
        profile_opt,
        __import__("os").environ.get("HERMES_JOBCTL_PROFILE"),
    )
    hb = hermes_bin or __import__("os").environ.get("HERMES_JOBCTL_HERMES_BIN")
    invoker = build_cron_context(p, hermes_bin=hb)
    print(f"profile: {p or 'default'}", file=sys.stderr)
    return p, invoker


def apply_paths(
    paths: list[Path],
    *,
    profile_opt: str | None,
    hermes_bin: str | None,
    accept_hooks: bool,
    verbose: bool,
) -> int:
    _, invoker = resolve_invoker(profile_opt, hermes_bin)
    errs: list[str] = []

    if verbose:
        print(f"jobs.json: {invoker.jobs_json_path}", file=sys.stderr)

    jobs = load_all_jobs(invoker.jobs_json_path)

    for tgt in paths:
        for md in iter_task_markdown_files(tgt):
            try:
                spec = parse_task_file(md)
                sj, cerr = singleton_job_or_error(jobs, spec.effective_name)
                if cerr:
                    raise OpError(cerr, md)
                if sj is None:
                    proc = run_cron(invoker, build_create_args(spec), accept_hooks=accept_hooks)
                    check_ok(proc, "hermes cron create")
                    print(f"[created] {md.name}: {spec.effective_name}")
                    jobs = load_all_jobs(invoker.jobs_json_path)
                    sj = find_jobs_by_name(jobs, spec.effective_name)
                    sj = sj[0] if len(sj) == 1 else None
                else:
                    proc = run_cron(invoker, build_edit_args(sj["id"], spec), accept_hooks=accept_hooks)
                    check_ok(proc, "hermes cron edit")
                    print(f"[updated] {md.name}: {spec.effective_name} ({sj.get('id')})")
                    jobs = load_all_jobs(invoker.jobs_json_path)
                    sj = next((x for x in jobs if x.get("id") == sj["id"]), sj)

                if sj is None:
                    raise OpError("job missing after mutation", md)

                if spec.suspend and not job_is_paused(sj):
                    proc = run_cron(invoker, build_pause_args(sj["id"]), accept_hooks=accept_hooks)
                    check_ok(proc, "hermes cron pause")
                elif (not spec.suspend) and job_is_paused(sj):
                    proc = run_cron(invoker, build_resume_args(sj["id"]), accept_hooks=accept_hooks)
                    check_ok(proc, "hermes cron resume")
            except (TaskSpecError, OpError, HermesCliError) as e:
                msg = str(e)
                errs.append(f"{md}: {msg}")
                print(f"error: {md}: {msg}", file=sys.stderr)
            except OSError as e:
                errs.append(f"{md}: {e}")
                print(f"error: {md}: {e}", file=sys.stderr)

    if errs:
        return 1
    return 0


def delete_targets(
    targets: list[Path],
    name: str | None,
    *,
    profile_opt: str | None,
    hermes_bin: str | None,
    accept_hooks: bool,
    verbose: bool,
) -> int:
    by_paths = len(targets) > 0
    by_name = name is not None
    if by_paths and by_name:
        raise ValueError("Provide either TASK paths or --name, not both.")
    if not by_paths and not by_name:
        raise ValueError("Provide at least one TASK path or --name NAME.")

    _, invoker = resolve_invoker(profile_opt, hermes_bin)
    if verbose:
        print(f"jobs.json: {invoker.jobs_json_path}", file=sys.stderr)

    if by_name:
        assert name is not None
        jobs = load_all_jobs(invoker.jobs_json_path)
        job, cerr = singleton_job_or_error(jobs, name)
        if cerr:
            print(f"error: {cerr}", file=sys.stderr)
            return 1
        if job is None:
            print(f"error: no job named {name!r}", file=sys.stderr)
            return 1
        proc = run_cron(invoker, build_remove_args(job["id"]), accept_hooks=accept_hooks)
        try:
            check_ok(proc, "hermes cron remove")
        except HermesCliError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"[removed] {name} ({job['id']})")
        return 0

    exit_code = 0
    for tgt in targets:
        try:
            for md in iter_task_markdown_files(tgt):
                jobs = load_all_jobs(invoker.jobs_json_path)
                try:
                    spec = parse_task_file(md)
                except TaskSpecError as e:
                    exit_code = 1
                    print(f"error: {md}: {e}", file=sys.stderr)
                    continue
                effective = spec.effective_name
                job, cerr = singleton_job_or_error(jobs, effective)
                if cerr:
                    exit_code = 1
                    print(f"error: {md}: {cerr}", file=sys.stderr)
                    continue
                if job is None:
                    exit_code = 1
                    print(f"error: {md}: no job named {effective!r}", file=sys.stderr)
                    continue
                proc = run_cron(invoker, build_remove_args(job["id"]), accept_hooks=accept_hooks)
                try:
                    check_ok(proc, "hermes cron remove")
                except HermesCliError as e:
                    exit_code = 1
                    print(f"error: {md}: {e}", file=sys.stderr)
                    continue
                print(f"[removed] {effective} ({job['id']})")
        except TaskSpecError as e:
            exit_code = 1
            print(f"error: {tgt}: {e}", file=sys.stderr)
    return exit_code


def status_paths(
    paths: list[Path],
    *,
    profile_opt: str | None,
    hermes_bin: str | None,
    json_out: bool,
    show_diff: bool,
    strict: bool,
    verbose: bool,
) -> int:
    _, invoker = resolve_invoker(profile_opt, hermes_bin)
    if verbose:
        print(f"jobs.json: {invoker.jobs_json_path}", file=sys.stderr)

    jobs = load_all_jobs(invoker.jobs_json_path)
    rows: list[dict[str, Any]] = []
    parse_errors = False
    strict_issues = False

    for tgt in paths:
        for md in iter_task_markdown_files(tgt):
            try:
                spec = parse_task_file(md)
                named = find_jobs_by_name(jobs, spec.effective_name)
                ambiguous = len(named) > 1
                job = named[0] if len(named) == 1 else None
                lbl = status_label(spec, job, ambiguous)
                if ambiguous:
                    if strict:
                        strict_issues = True
                    ids = ", ".join(str(j.get("id")) for j in named)
                    note = f"multiple jobs: {ids}"
                    jid = ids
                elif job is None:
                    if strict:
                        strict_issues = True
                    note = ""
                    jid = ""
                else:
                    d = desired_from_spec(spec)
                    df = drift_fields(d, job)
                    if lbl == "pending_apply" and strict:
                        strict_issues = True
                    note = ", ".join(df) if df else ""
                    if show_diff and "prompt" in df and verbose:
                        note += " (prompt differs)"
                    jid = str(job.get("id", ""))
                rows.append(
                    {
                        "file": str(md),
                        "name": spec.effective_name,
                        "status": lbl,
                        "job_id": jid,
                        "notes": note,
                    }
                )
            except TaskSpecError as e:
                parse_errors = True
                rows.append(
                    {"file": str(md), "name": "", "status": "error", "job_id": "", "notes": str(e)}
                )

    if json_out:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        w = [
            len(str(max((r["file"] for r in rows), key=len))),
            len(str(max((r["name"] for r in rows), key=len))),
            len(str(max((r["status"] for r in rows), key=len))),
            len(str(max((str(r["job_id"]) for r in rows), key=len))),
        ] if rows else [4, 4, 6, 6]
        hdr = f"{'FILE':<{w[0]}}  {'NAME':<{w[1]}}  {'STATUS':<{w[2]}}  {'JOB_ID':<{w[3]}}  NOTES"
        print(hdr)
        print("-" * min(120, len(hdr)))
        for r in rows:
            print(
                f"{r['file']:<{w[0]}}  {r['name']:<{w[1]}}  "
                f"{r['status']:<{w[2]}}  {str(r['job_id']):<{w[3]}}  {r['notes']}"
            )

    if parse_errors or (strict and strict_issues):
        return 1
    return 0


def get_cmd(
    name: str | None,
    *,
    profile_opt: str | None,
    hermes_bin: str | None,
    json_out: bool,
    verbose: bool,
) -> int:
    _, invoker = resolve_invoker(profile_opt, hermes_bin)
    if verbose:
        print(f"jobs.json: {invoker.jobs_json_path}", file=sys.stderr)

    jobs = load_all_jobs(invoker.jobs_json_path)
    if name:
        jobs = find_jobs_by_name(jobs, name)
    if json_out:
        print(json.dumps(jobs, indent=2, ensure_ascii=False))
        return 0

    if not jobs:
        print("(no matching jobs)")
        return 0
    for j in jobs:
        print(f"{j.get('id')}  {j.get('name')}  {j.get('schedule_display') or '?'}")
    return 0
