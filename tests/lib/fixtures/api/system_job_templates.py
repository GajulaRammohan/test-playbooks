import pytest


@pytest.fixture(scope="function", params=['cleanup_jobs', 'cleanup_activitystream', 'cleanup_facts'])
def system_job_template(request):
    return request.getfuncargvalue(request.param + '_template')


@pytest.fixture(scope="function")
def cleanup_jobs_template(api_system_job_templates_pg):
    """Return the cleanup job details system job template."""
    matches = api_system_job_templates_pg.get(job_type='cleanup_jobs')
    assert matches.count == 1, "No cleanup job details system JT found."
    return matches.results.pop()


@pytest.fixture(scope="function")
def cleanup_activitystream_template(api_system_job_templates_pg):
    """Return the cleanup activity stream system job template."""
    matches = api_system_job_templates_pg.get(job_type='cleanup_activitystream')
    assert matches.count == 1, "No cleanup activity stream system JT found."
    return matches.results.pop()


@pytest.fixture(scope="function")
def cleanup_facts_template(api_system_job_templates_pg):
    """Return the cleanup fact details system job template."""
    matches = api_system_job_templates_pg.get(job_type='cleanup_facts')
    assert matches.count == 1, "No cleanup fact details system JT found."
    return matches.results.pop()
