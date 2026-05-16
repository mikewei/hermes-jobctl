from hermes_jobctl.state import find_job_by_id, find_jobs_by_name, singleton_job_or_error


def test_singleton_ambiguous():
    jobs = [{"id": "1", "name": "x"}, {"id": "2", "name": "x"}]
    j, err = singleton_job_or_error(jobs, "x")
    assert j is None
    assert err and "multiple" in err


def test_singleton_one():
    jobs = [{"id": "9", "name": "only"}]
    j, err = singleton_job_or_error(jobs, "only")
    assert err is None
    assert j["id"] == "9"


def test_find_job_by_id_hit():
    jobs = [{"id": "abc123", "name": "x"}, {"id": "other", "name": "y"}]
    j = find_job_by_id(jobs, "abc123")
    assert j is not None
    assert j["name"] == "x"


def test_find_job_by_id_miss():
    jobs = [{"id": "1", "name": "x"}]
    assert find_job_by_id(jobs, "missing") is None


def test_find_job_by_id_strips_whitespace():
    jobs = [{"id": "1", "name": "x"}]
    j = find_job_by_id(jobs, " 1 ")
    assert j is not None
    assert j["id"] == "1"
