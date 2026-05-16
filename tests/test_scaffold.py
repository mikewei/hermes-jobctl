import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from hermes_jobctl.drift import DesiredState, drift_fields
from hermes_jobctl.profile import CronInvoker
from hermes_jobctl.scaffold import (
    render_spec_from_job,
    render_spec_template,
    run_new,
    stem_from_job_name,
    validate_task_stem,
)
from hermes_jobctl.spec import parse_task_file, parse_task_text
from tests.test_drift import sample_job

_NEW_KW = dict(
    from_job_id=None,
    profile_opt=None,
    hermes_bin=None,
    verbose=False,
)


def _mock_invoker(monkeypatch, jobs_path: Path) -> None:
    inv = CronInvoker(("hermes", "cron"), jobs_path)

    def _resolve(_profile_opt, _hermes_bin):
        return None, inv

    monkeypatch.setattr("hermes_jobctl.commands.resolve_invoker", _resolve)


def test_validate_rejects_empty():
    with pytest.raises(ValueError):
        validate_task_stem("  ")


def test_validate_strips_md_suffix():
    assert validate_task_stem("foo.md") == "foo"


def test_template_contains_keys():
    t = render_spec_template(stem="demo", schedule="1h")
    assert "type: hermes-cron" in t
    assert 'schedule: "1h"' in t
    assert "deliver" in t
    assert "suspend" in t
    assert t.startswith("---")


def test_template_default_schedule():
    t = render_spec_template(stem="demo", schedule="")
    assert 'schedule: "every 24h"' in t


def test_run_new_writes(tmp_path):
    code = run_new(
        "alpha",
        directory=tmp_path,
        output=None,
        schedule="30m",
        force=False,
        stdout_flag=False,
        **_NEW_KW,
    )
    assert code == 0
    p = tmp_path / "alpha.md"
    assert p.is_file()
    assert "30m" in p.read_text(encoding="utf-8")

    assert (
        run_new(
            "alpha",
            directory=tmp_path,
            output=None,
            schedule="30m",
            force=False,
            stdout_flag=False,
            **_NEW_KW,
        )
        == 1
    )
    assert (
        run_new(
            "alpha",
            directory=tmp_path,
            output=None,
            schedule="30m",
            force=True,
            stdout_flag=False,
            **_NEW_KW,
        )
        == 0
    )


def test_run_new_default_schedule(tmp_path):
    code = run_new(
        "defaults",
        directory=tmp_path,
        output=None,
        schedule=None,
        force=False,
        stdout_flag=False,
        **_NEW_KW,
    )
    assert code == 0
    assert "every 24h" in (tmp_path / "defaults.md").read_text(encoding="utf-8")


def test_stdout(tmp_path):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = run_new(
            "beta",
            directory=None,
            output=None,
            schedule="every 2h",
            force=False,
            stdout_flag=True,
            **_NEW_KW,
        )
    assert code == 0
    assert "every 2h" in buf.getvalue()
    assert not (tmp_path / "beta.md").exists()


def test_new_file_parses(tmp_path):
    run_new(
        "parsed",
        directory=tmp_path,
        output=None,
        schedule="5m",
        force=False,
        stdout_flag=False,
        **_NEW_KW,
    )
    spec = parse_task_file(tmp_path / "parsed.md")
    assert spec.effective_name == "parsed"
    assert spec.schedule == "5m"


def test_dir_and_output_conflict():
    code = run_new(
        "x",
        directory=Path("/tmp"),
        output=Path("/tmp/y.md"),
        schedule="1h",
        force=False,
        stdout_flag=False,
        **_NEW_KW,
    )
    assert code == 2


def test_output_path_stem_in_comment(tmp_path):
    sub = tmp_path / "out"
    sub.mkdir()
    target = sub / "gamma.md"
    code = run_new(
        "ignored-stem",
        directory=None,
        output=target,
        schedule="1h",
        force=False,
        stdout_flag=False,
        **_NEW_KW,
    )
    assert code == 0
    assert "'gamma'" in target.read_text(encoding="utf-8")


def test_task_name_required_without_from_job():
    code = run_new(
        None,
        directory=None,
        output=None,
        schedule=None,
        force=False,
        stdout_flag=False,
        **_NEW_KW,
    )
    assert code == 2


def test_stem_from_job_name_sanitizes():
    assert stem_from_job_name("foo/bar") == "foo_bar"


def test_stem_from_job_name_rejects_empty():
    with pytest.raises(ValueError, match="no name"):
        stem_from_job_name("  ")


def test_render_spec_from_job_fields():
    job = sample_job()
    text = render_spec_from_job(job, stem="sample-cron-task")
    assert 'schedule: "every 24h"' in text
    assert 'deliver: "local"' in text
    assert "name:" not in text.split("---")[1]
    assert text.endswith("hello\n")


def test_render_spec_from_job_includes_name_when_stem_differs():
    job = sample_job()
    text = render_spec_from_job(job, stem="other-stem")
    assert 'name: "sample-cron-task"' in text


def test_render_spec_from_job_round_trip_no_drift(tmp_path):
    job = sample_job()
    text = render_spec_from_job(job, stem="sample-cron-task")
    spec = parse_task_text(tmp_path / "t.md", text)
    d = DesiredState(
        schedule=spec.schedule,
        prompt=spec.prompt_body,
        deliver=spec.deliver,
        repeat=spec.repeat,
        skills=spec.skills,
        script=spec.script,
        workdir=spec.workdir,
        suspend=spec.suspend,
    )
    assert drift_fields(d, job) == []


def test_from_job_and_schedule_conflict():
    code = run_new(
        "x",
        from_job_id="abc123",
        schedule="1h",
        directory=None,
        output=None,
        force=False,
        stdout_flag=False,
        profile_opt=None,
        hermes_bin=None,
        verbose=False,
    )
    assert code == 2


def test_from_job_not_found(tmp_path, monkeypatch):
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text("[]", encoding="utf-8")
    _mock_invoker(monkeypatch, jobs_file)
    code = run_new(
        None,
        from_job_id="missing",
        directory=tmp_path,
        output=None,
        schedule=None,
        force=False,
        stdout_flag=False,
        profile_opt=None,
        hermes_bin=None,
        verbose=False,
    )
    assert code == 1


def test_run_new_from_job_default_stem(tmp_path, monkeypatch):
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(json.dumps([sample_job()]), encoding="utf-8")
    _mock_invoker(monkeypatch, jobs_file)
    code = run_new(
        None,
        from_job_id="abc123",
        directory=tmp_path,
        output=None,
        schedule=None,
        force=False,
        stdout_flag=False,
        profile_opt=None,
        hermes_bin=None,
        verbose=False,
    )
    assert code == 0
    out = tmp_path / "sample-cron-task.md"
    assert out.is_file()
    spec = parse_task_file(out)
    assert spec.effective_name == "sample-cron-task"
    assert spec.schedule == "every 24h"
    assert spec.prompt_body == "hello"


def test_run_new_from_job_explicit_stem(tmp_path, monkeypatch):
    jobs_file = tmp_path / "jobs.json"
    jobs_file.write_text(json.dumps([sample_job()]), encoding="utf-8")
    _mock_invoker(monkeypatch, jobs_file)
    code = run_new(
        "my-copy",
        from_job_id="abc123",
        directory=tmp_path,
        output=None,
        schedule=None,
        force=False,
        stdout_flag=False,
        profile_opt=None,
        hermes_bin=None,
        verbose=False,
    )
    assert code == 0
    text = (tmp_path / "my-copy.md").read_text(encoding="utf-8")
    assert 'name: "sample-cron-task"' in text
