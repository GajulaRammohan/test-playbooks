import pytest


@pytest.fixture(scope="function", params=['cleanup_jobs', 'cleanup_deleted', 'cleanup_activitystream'])
def system_job(request):
    return request.getfuncargvalue(request.param)


@pytest.fixture(scope="function")
def cleanup_jobs(request, cleanup_jobs_template):
    payload = dict()

    # optionally override days
    fixture_args = getattr(request.function, 'fixture_args', None)
    if fixture_args and fixture_args.kwargs.get('days', False):
        payload.update(extra_vars=dict(days=fixture_args.kwargs['days']))

    return cleanup_jobs_template.launch(payload)


@pytest.fixture(scope="function")
def cleanup_jobs_with_status_completed(cleanup_jobs):
    return cleanup_jobs.wait_until_completed()


@pytest.fixture(scope="function")
def cleanup_deleted(request, cleanup_deleted_template):
    payload = dict()

    # optionally override days
    fixture_args = getattr(request.function, 'fixture_args', None)
    if fixture_args and fixture_args.kwargs.get('days', False):
        payload.update(extra_vars=dict(days=fixture_args.kwargs['days']))

    return cleanup_deleted_template.launch(payload)
    return None


@pytest.fixture(scope="function")
def cleanup_deleted_with_status_completed(cleanup_deleted):
    return cleanup_deleted.wait_until_completed()


@pytest.fixture(scope="function")
def cleanup_activitystream(request, cleanup_activitystream_template):
    payload = dict()

    # optionally override days
    fixture_args = getattr(request.function, 'fixture_args', None)
    if fixture_args and fixture_args.kwargs.get('days', False):
        payload.update(extra_vars=dict(days=fixture_args.kwargs['days']))

    return cleanup_activitystream_template.launch(payload)
    return None


@pytest.fixture(scope="function")
def cleanup_activitystream_with_status_completed(cleanup_activitystream):
    return cleanup_activitystream.wait_until_completed()
