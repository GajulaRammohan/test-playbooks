import logging
import re
import time

import pytest
from towerkit import utils

from tests.api import APITest


log = logging.getLogger(__name__)


@pytest.mark.second
@pytest.mark.api
@pytest.mark.destructive
@pytest.mark.skip_openshift
@pytest.mark.mp_group('AnsibleTowerService', 'isolated_serial')
class TestTowerServices(APITest):
    pytestmark = pytest.mark.usefixtures('authtoken')

    @pytest.mark.parametrize("command, active", [
        ("start", True),
        ("stop", False),
        ("restart", True),
        ("status", True)
    ], ids=['ansible-tower-service start', 'ansible-tower-service stop', 'ansible-tower-service restart', 'ansible-tower-service status'])
    def test_tower_status_on_el7(self, ansible_runner, ansible_os_family, restart_tower_on_teardown, command, active):
        """Executes ansible-tower-service commands and checks process statuses.
        Note: we check process output with systemctl on EL7 systems and with
        service on EL6 systems. Did not implement with Ubuntu because of the
        following:
        * On Ubuntu systems, ansible-tower-service status sometimes incorrectly
        reports the status of redis-server.
        * On Ubuntu systems, rapidly restarting supervisor can leave your system
        in an indeterminate state.
        """
        # check that Tower is running on an EL system
        if not (ansible_os_family == 'RedHat'):
            pytest.skip("Only supported on EL distributions")

        # issue ansible-tower-service command
        contacted = ansible_runner.command('ansible-tower-service ' + command)
        result = contacted.values()[0]
        assert result['rc'] == 0, "ansible-tower-service {0} failed. Command stderr: \n{1}".format(command, result['stderr'])

        # determine expected_processes
        contacted = ansible_runner.shell('cat /etc/sysconfig/ansible-tower')
        stdout = contacted.values()[0]['stdout']
        match = re.search("TOWER_SERVICES=\"(.*?)\"", stdout)
        processes = match.group(1).split()

        # assess process statuses
        for process in processes:
            contacted = ansible_runner.command('systemctl status {}'.format(process))
            result = contacted.values()[0]
            assert ("Active: active (running)" in result['stdout']) is active, \
                u"Unexpected process status for process {0} after executing ansible-tower-service {1}\n\nstdout:\n{2}"\
                .format(process, command, result['stdout'])

    def test_tower_restart(self, install_enterprise_license_unlimited, factories, v2, ansible_runner):
        jt = factories.v2_job_template(playbook='sleep.yml',
                                       extra_vars=dict(sleep_interval=60))
        jt.ds.inventory.add_host()
        self.ensure_jt_runs_on_primary_instance(jt, v2)
        job = jt.launch().wait_until_status('running')

        try:
            contacted = ansible_runner.command('ansible-tower-service stop')
            result = contacted.values()[0]
            assert result['rc'] == 0, "ansible-tower-service {0} failed. Command stderr: \n{1}".format(result['stderr'])
            time.sleep(30)
        finally:
            contacted = ansible_runner.command('ansible-tower-service start')
            result = contacted.values()[0]
            assert result['rc'] == 0, "ansible-tower-service {0} failed. Command stderr: \n{1}".format(result['stderr'])

        def online():
            try:
                v2.get()
                # API can be up and the job still give a BadGateway error for a
                # few seconds.
                job.get()
            except:
                return False
            return True
        utils.poll_until(online, interval=5, timeout=120)
        job.wait_until_status('failed', since_job_created=False)
        assert job.job_explanation == 'Task was marked as running in Tower but was not present in the job queue, so it has been marked as failed.'

        jt.extra_vars = '{"sleep_interval": 1}'
        job = jt.launch().wait_until_completed()
        job.assert_successful(msg='Newly launched job was not successful after ansible-tower-service restart!')

    def test_rabbitmq_unavailable(self, install_enterprise_license_unlimited,
                                  factories, v2, ansible_runner, ansible_os_family):
        jt = factories.v2_job_template(playbook='sleep.yml',
                                       extra_vars=dict(sleep_interval=60))
        jt.ds.inventory.add_host()
        # Important to run jt on same node where we stop rabbitmq because
        # Each Tower instance has a deployment of RabbitMQ that will cluster
        # with the other instances' RabbitMQ instances.
        self.ensure_jt_runs_on_primary_instance(jt, v2)
        job = jt.launch().wait_until_status('running')

        try:
            contacted = ansible_runner.service(name='rabbitmq-server', state='stopped')
            result = contacted.values()[0]
            assert not result.get('failed', False), \
                "Stopping rabbitmq failed. Command stderr: \n{0}\n\nCommand stdout: \n{1}"\
                .format(result['stderr'], result['stdout'])
            assert 'Could not find the requested service' not in result.get('msg', '')
            time.sleep(30)
        finally:
            contacted = ansible_runner.service(name='rabbitmq-server', state='started')
            result = contacted.values()[0]
            assert not result.get('failed', False), \
                "Starting rabbitmq failed. Command stderr: \n{0}\n\nCommand stdout: \n{1}"\
                .format(result['stderr'], result['stdout'])
            assert 'Could not find the requested service' not in result.get('msg', '')
            # Let rabbitmq-server warm up
            time.sleep(20)

        # Rabbit being down and restarting will not effect the responsiveness
        # of v2.get(), so it does not help us to wait for it.
        # we are waiting for a job that was given a sleep interval of 120 to
        # complete. This is to give rabbit enough time to be shut down and
        # restarted.
        job.wait_until_status('successful', since_job_created=False, timeout=190)

        # On this second run we should not have to wait so long
        jt.extra_vars = '{"sleep_interval": 1}'
        job = jt.launch().wait_until_completed()
        job.assert_successful(msg='Newly launched job was not successful after rabbitmq restart!')

        # Test that we can create new job templates and run them
        new_jt = factories.v2_job_template(playbook='sleep.yml',
                                       extra_vars=dict(sleep_interval=1))
        new_job = new_jt.launch().wait_until_completed()
        new_job.assert_successful(msg='Job launched from newly created JT after rabbitmq restart failed!')

    def test_database_unavailable(self, install_enterprise_license_unlimited,
                                  factories, v2, ansible_adhoc, ansible_os_family):
        if ansible_os_family == 'Debian':
            pg_service = 'postgresql'
        else:
            pg_service = 'postgresql-9.6'
        jt = factories.v2_job_template(playbook='sleep.yml',
                                       extra_vars=dict(sleep_interval=120))
        jt.ds.inventory.add_host()
        job = jt.launch().wait_until_status('running')

        # We need to find the right host to stop the postgres server on
        tower_hosts = ansible_adhoc()
        if tower_hosts.has_matching_inventory('database'):
            db_host = tower_hosts.database
        elif tower_hosts.has_matching_inventory('tower'):
            db_host = tower_hosts.tower
        else:
            raise KeyError(
                'Could not find a host in the inventory to stop the database'
                '\non! Provide an inventory for a standalone tower with a '
                '"tower" group or a cluster with a "database" group.')

        try:
            contacted = db_host.service(name=pg_service, state='stopped')
            result = contacted.values()[0]
            assert not result.get('failed', False), \
                "Stopping postgres failed. Command stderr: \n{0}\n\nCommand stdout: \n{1}"\
                .format(result['stderr'], result['stdout'])
            assert 'Could not find the requested service' not in result.get('msg', '')
            time.sleep(60)
        finally:
            contacted = db_host.service(name=pg_service, state='started')
            result = contacted.values()[0]
            assert not result.get('failed', False), \
                "Starting postgres failed. Command stderr: \n{0}\n\nCommand stdout: \n{1}"\
                .format(result['stderr'], result['stdout'])
            assert 'Could not find the requested service' not in result.get('msg', '')
            time.sleep(20)

        def online():
            try:
                v2.get()
                # API can be up and the job still give a BadGateway error for a
                # few seconds.
                job.get()
            except:
                return False
            return True
        utils.poll_until(online, interval=5, timeout=120)
        # We are waiting for a job that was given a sleep interval of 120 to
        # complete. This is to give postgres enough time to be shut down and
        # restarted.
        job.wait_until_status(['error', 'failed'], since_job_created=False, timeout=190)

        # behavior here is _not_ deterministic; when the database has
        # a prolonged outage, a job _could_ land in _either_ failed state or
        # error state, depending on where it is in execution at the time of the
        # DB outage
        #
        # For example, if the database goes down while we're still running
        # RunJob.run(), we might encounter an exception while accessing the
        # (unavailable) database.  In this scenario, Tower has code that
        # attempts to set Job.status = 'error' with a periodic retry loop.
        # Depending on when the database becomes available again, _sometimes_
        # this code path wins and sets the Job status to 'error'.
        #
        # Other times, before this retry loop is successful, the dispatcher
        # wakes up - via its periodic heartbeat - and notices the dead job and
        # marks it as status = 'failed' via reaper code - sometimes _this_ code
        # path wins.
        #
        # the *main* thing we want to verify is that when the database goes
        # down, the job enters _some_ form of failure state, and doesn't
        # get stuck in a perpetual running state
        if job.get().status == 'failed':
            assert job.job_explanation == 'Task was marked as running in Tower but was not present in the job queue, so it has been marked as failed.'

        # Test that we can create new job templates and run them
        new_jt = factories.v2_job_template(playbook='sleep.yml',
                                       extra_vars=dict(sleep_interval=1))
        new_job = new_jt.launch().wait_until_completed()
        new_job.assert_successful(msg='Job launched from newly created JT after DB restart failed!')

        jt.extra_vars = '{"sleep_interval": 1}'
        job = jt.launch().wait_until_completed()
        job.assert_successful(msg='Newly launched job from old job template was not successful after database restart!')
