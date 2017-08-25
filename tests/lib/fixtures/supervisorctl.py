import logging
import json
import pytest


log = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def pause_awx_task_system(request, is_docker, ansible_runner):
    """Stops awx-task-system and restarts it upon teardown. Aids our cancel tests.

    Note: this is about as noisy of a neighbor a test can be.  Its worth should be re-evaluated:
    1. Stopping celery will halt task processing tower activity (the point of the fixture) but this will
       break other tests if multiprocessing is running.
    2. Failing to stop the awx-celeryd service will exit pytest, killing the test run.
    3. Having to halt a critical part of tower to confirm pending jobs can be canceled seems like a bad approach.
    """
    if is_docker:
        pytest.skip("Pausing task system isn't supported by AWX container.")

    def teardown():
        log.debug("calling supervisorctl teardown pause_awx_task_system")
        contacted = ansible_runner.supervisorctl(name='tower-processes:awx-celeryd', state='started')
        result = contacted.values()[0]
        if result.get('failed'):
            pytest.exit("tower-processes:awx-celeryd failed to restart - {0}.".format(json.dumps(result, indent=2)))
    request.addfinalizer(teardown)

    log.debug("calling supervisorctl fixture pause_awx_task_system")
    contacted = ansible_runner.supervisorctl(name='tower-processes:awx-celeryd', state='stopped')
    result = contacted.values()[0]
    assert(not result.get('failed')
           ), "Stopping tower-processes:awx-celeryd failed - {0}.".format(json.dumps(result, indent=2))
