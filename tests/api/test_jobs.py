# -*- coding: utf-8 -*-
import logging
import types
import json
import re

from towerkit.config import config
from towerkit import exceptions as exc
import fauxfactory
import pytest

from tests.api import APITest


log = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def job_sleep(request, job_template_sleep):
    """Launch the job_template_sleep and return a job resource."""
    return job_template_sleep.launch()


@pytest.fixture(scope="function")
def job_with_status_pending(job_template_sleep, pause_awx_task_system):
    """Wait for job_sleep to move from new to queued, and return the job."""
    return job_template_sleep.launch().wait_until_started()


@pytest.fixture(scope="function")
def job_with_status_running(request, job_sleep):
    """Wait for job_sleep to move from queued to running, and return the job."""
    return job_sleep.wait_until_status('running')


@pytest.fixture(scope="function")
def job_with_multi_ask_credential_and_password_in_payload(request, job_template_multi_ask):
    """Launch job_template_multi_ask with passwords in the payload."""
    launch_pg = job_template_multi_ask.get_related("launch")

    # determine whether sudo or su was used
    credential = job_template_multi_ask.get_related('credential')

    # assert expected values in launch_pg.passwords_needed_to_start
    assert credential.expected_passwords_needed_to_start == launch_pg.passwords_needed_to_start

    # build launch payload
    payload = dict(ssh_password=config.credentials['ssh']['password'],
                   ssh_key_unlock=config.credentials['ssh']['encrypted']['ssh_key_unlock'],
                   become_password=config.credentials['ssh']['become_password'])

    # launch job_template
    result = launch_pg.post(payload)

    # find and return specific job_pg
    jobs_pg = job_template_multi_ask.get_related('jobs', id=result.json['job'])
    assert jobs_pg.count == 1, "Unexpected number of jobs returned (%s != 1)" % jobs_pg.count
    return jobs_pg.results[0]


@pytest.fixture(scope="function", params=['project', 'inventory'])
def job_with_deleted_related(request, job_with_status_completed):
    """Creates and deletes an related attribute of a job"""
    related_pg = job_with_status_completed.get_related(request.param)
    related_pg.delete()
    if request.param == 'inventory':
        related_pg.wait_until_deleted()
    return job_with_status_completed


@pytest.fixture()
def utf8_template(request, authtoken, api_job_templates_pg, project_ansible_playbooks_git, host_local, ssh_credential):
    payload = dict(name="playbook:utf-8.yml.yml, random:%s" % (fauxfactory.gen_utf8()),
                   description="utf-8.yml - %s" % (fauxfactory.gen_utf8()),
                   inventory=host_local.inventory,
                   job_type='run',
                   project=project_ansible_playbooks_git.id,
                   credential=ssh_credential.id,
                   playbook='utf-8-䉪ቒ칸ⱷꯔ噂폄蔆㪗輥.yml',)
    obj = api_job_templates_pg.post(payload)
    request.addfinalizer(obj.delete)
    return obj


@pytest.fixture(scope="function")
def project_with_scm_update_on_launch(request, project_ansible_playbooks_git):
    return project_ansible_playbooks_git.patch(scm_update_on_launch=True)


@pytest.fixture(scope="function")
def job_template_with_cloud_credential(request, job_template, cloud_credential):
    job_template.patch(cloud_credential=cloud_credential.id)
    return job_template


@pytest.fixture(scope="function")
def job_template_with_network_credential(request, job_template, network_credential):
    job_template.patch(network_credential=network_credential.id)
    return job_template


@pytest.fixture(scope="function")
def expected_net_env_vars():
    """Returns a list of our expected network job env variables."""
    def func(network_credential):
        expected_env_vars = dict()
        if getattr(network_credential, "username", None):
            expected_env_vars["ANSIBLE_NET_USERNAME"] = config.credentials['network']['username']
        if getattr(network_credential, "password", None):
            expected_env_vars["ANSIBLE_NET_PASSWORD"] = "**********"
        if getattr(network_credential, "ssh_key_data", None):
            expected_env_vars["ANSIBLE_NET_SSH_KEYFILE"] = "**********"
        if getattr(network_credential, "authorize", None):
            expected_env_vars["ANSIBLE_NET_AUTHORIZE"] = "1"
        else:
            expected_env_vars["ANSIBLE_NET_AUTHORIZE"] = "0"
        if getattr(network_credential, "authorize_password", None):
            expected_env_vars["ANSIBLE_NET_AUTH_PASS"] = "**********"
        return expected_env_vars
    return func


def confirm_job_env(job_pg, expected_env_vars):
    """Convenience function to assess that the correct job environment variables
    are present and have the correct values.
    """
    for env_var, env_val in expected_env_vars.items():
        assert env_var in job_pg.job_env, "Missing expected environment variable %s in job_env.\n%s" % \
            (env_var, json.dumps(job_pg.job_env, indent=2))

        if isinstance(env_val, types.FunctionType):
            is_correct = env_val(job_pg.job_env[env_var])
        else:
            is_correct = job_pg.job_env[env_var] == env_val
        assert is_correct, "Unexpected value for environment variable %s in job_env ('%s')." % \
            (env_var, job_pg.job_env[env_var])


def azure_type(azure_credential):
    """Convenience function that returns our type of new-style Azure credential"""
    azure_attrs = ['subscription', 'tenant', 'secret', 'client']
    azure_ad_attrs = ['subscription', 'username', 'password']
    if all([getattr(azure_credential, attr, None) for attr in azure_attrs]):
        return 'azure'
    elif all([getattr(azure_credential, attr, None) for attr in azure_ad_attrs]):
        return 'azure_ad'
    else:
        raise ValueError("Unhandled credential received - %s." % azure_credential)


@pytest.mark.api
@pytest.mark.destructive
@pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')
class Test_Job(APITest):

    @pytest.mark.ansible_integration
    def test_utf8(self, utf8_template):
        """Verify that a playbook full of UTF-8 successfully works through Tower"""
        # launch job
        job_pg = utf8_template.launch_job()

        # wait for completion
        job_pg = job_pg.wait_until_completed(timeout=60 * 10)

        # assert successful completion of job
        job_pg.assert_successful()

    def test_relaunch_with_credential(self, job_with_status_completed):
        """Verify relaunching a job with a valid credential no-ask credential."""
        relaunch_pg = job_with_status_completed.get_related('relaunch')

        # assert values on relaunch resource
        assert not relaunch_pg.passwords_needed_to_start

        # relaunch the job and wait for completion
        job_pg = job_with_status_completed.relaunch().wait_until_completed()

        # assert success
        job_pg.assert_successful()

    def test_relaunch_with_different_custom_credential(self, request, v2, factories):
        """Verify relaunching a job when a custom credential associated with the template
        has been changed to another of the same type"""
        jt = factories.v2_job_template()
        custom_cred_type = factories.credential_type()

        custom_cred1, custom_cred2 = [factories.v2_credential(credential_type=custom_cred_type) for _ in range(2)]
        jt.add_extra_credential(custom_cred1)

        job = jt.launch().wait_until_completed()
        job.assert_successful()

        jt.remove_extra_credential(custom_cred1)
        jt.add_extra_credential(custom_cred2)

        relaunched_job = job.relaunch().wait_until_completed()
        relaunched_job.assert_successful()

        creds_used = [c['id']
                      for c in relaunched_job.summary_fields.credentials]
        assert custom_cred1.id not in creds_used
        assert custom_cred2.id in creds_used

    def test_relaunch_with_vault_credential_only(self, request, factories, v2):
        payload = factories.v2_job_template.payload()
        del payload['credential']

        vault_credential = factories.v2_credential(kind='vault', vault_password='tower')
        payload['vault_credential'] = vault_credential.id
        payload['playbook'] = 'vaulted_debug_hostvars.yml'

        jt = v2.job_templates.post(payload)
        request.addfinalizer(jt.delete)
        factories.v2_host(inventory=jt.ds.inventory)

        job = jt.launch().wait_until_completed()
        job.assert_successful()

        relaunched_job = job.relaunch().wait_until_completed()
        relaunched_job.assert_successful()

    def test_relaunch_with_deleted_related(self, job_with_deleted_related):
        """Verify relaunching a job whose related information has been deleted."""
        # get relaunch page
        relaunch_pg = job_with_deleted_related.get_related('relaunch')

        # assert values on relaunch resource
        assert not relaunch_pg.passwords_needed_to_start

        # attempt to relaunch the job, should raise exception
        with pytest.raises(exc.BadRequest):
            relaunch_pg.post()

    def test_relaunch_with_multi_ask_credential_and_passwords_in_payload(self, job_with_multi_ask_credential_and_password_in_payload):  # NOQA
        """Verify that relaunching a job with a credential that includes ASK passwords, behaves as expected when
        supplying the necessary passwords in the relaunch payload.
        """
        # get relaunch page
        relaunch_pg = job_with_multi_ask_credential_and_password_in_payload.get_related('relaunch')

        # determine expected passwords
        credential = job_with_multi_ask_credential_and_password_in_payload.get_related('credential')

        # assert expected values in relaunch_pg.passwords_needed_to_start
        assert credential.expected_passwords_needed_to_start == relaunch_pg.passwords_needed_to_start

        # relaunch the job and wait for completion
        payload = dict(ssh_password=config.credentials['ssh']['password'],
                       ssh_key_unlock=config.credentials['ssh']['encrypted']['ssh_key_unlock'],
                       become_password=config.credentials['ssh']['become_password'])
        job_pg = job_with_multi_ask_credential_and_password_in_payload.relaunch(payload).wait_until_completed()

        # assert success
        job_pg.assert_successful()

    def test_relaunch_with_multi_ask_credential_and_without_passwords(self, job_with_multi_ask_credential_and_password_in_payload):  # NOQA
        """Verify that relaunching a job with a multi-ask credential fails when not supplied with passwords."""
        # get relaunch page
        relaunch_pg = job_with_multi_ask_credential_and_password_in_payload.get_related('relaunch')

        # determine expected passwords
        credential = job_with_multi_ask_credential_and_password_in_payload.get_related('credential')

        # assert expected values in relaunch_pg.passwords_needed_to_start
        assert credential.expected_passwords_needed_to_start == relaunch_pg.passwords_needed_to_start

        # relaunch the job
        exc_info = pytest.raises(exc.BadRequest, relaunch_pg.post, {})
        result = exc_info.value[1]

        # assert expected error responses
        assert 'Missing passwords needed to start' in result['credential_passwords'][0], \
            "Expecting 'Missing passwords needed to start' in API response when " \
            "relaunching a job, without provided credential " \
            "passwords. %s" % json.dumps(result)

        # assert expected values in response
        expected_passwords = result['credential_passwords'][0].split(':')[1]
        expected_password_list = expected_passwords.replace(' ', '').split(',')
        assert sorted(credential.expected_passwords_needed_to_start) == sorted(expected_password_list)

    def test_relaunch_uses_extra_vars_from_job(self, job_with_extra_vars):
        """Verify that when you relaunch a job containing extra_vars in the
        launch-time payload, the resulting extra_vars *and* the job_template
        extra_vars are used.
        """
        relaunch_pg = job_with_extra_vars.get_related('relaunch')

        # assert values on relaunch resource
        assert not relaunch_pg.passwords_needed_to_start

        # relaunch the job and wait for completion
        relaunched_job_pg = job_with_extra_vars.relaunch().wait_until_completed()

        # assert success
        relaunched_job_pg.assert_successful()

        # coerce extra_vars into a dictionary
        try:
            job_extra_vars = json.loads(job_with_extra_vars.extra_vars)
        except ValueError:
            job_extra_vars = {}

        try:
            relaunch_extra_vars = json.loads(relaunched_job_pg.extra_vars)
        except ValueError:
            relaunch_extra_vars = {}

        # assert the extra_vars on the relaunched job, match the extra_vars
        # used in the original job
        assert set(relaunch_extra_vars) == set(job_extra_vars), \
            "The extra_vars on a relaunched job should match the extra_vars on the job being relaunched (%s != %s)" % \
            (relaunch_extra_vars, job_extra_vars)

    def test_cannot_relaunch_with_inventory_with_pending_deletion(self, factories):
        jt = factories.v2_job_template()
        inv = jt.ds.inventory
        factories.v2_host(inventory=inv)

        job = jt.launch().wait_until_completed()
        job.assert_successful()

        inv.delete().wait_until_deleted()
        with pytest.raises(exc.BadRequest) as e:
            job.relaunch()
        assert e.value[1]['errors'] == ['Job Template Inventory is missing or undefined.']

    def test_relaunched_jobs_are_based_on_source_template_with_prompts(self, factories):
        jt = factories.v2_job_template(ask_limit_on_launch=True)
        job = jt.launch(payload=dict(limit='foobar')).wait_until_completed()
        job.assert_successful()
        assert json.loads(job.extra_vars) == {}

        jt.extra_vars = '{"key": "value"}'
        relaunched_job = job.relaunch().wait_until_completed()
        relaunched_job.assert_successful()
        assert json.loads(relaunched_job.extra_vars) == {"key": "value"}
        assert relaunched_job.limit == "foobar"

    def test_superuser_can_relaunch_orphan_jobs(self, factories):
        jt = factories.v2_job_template(
            limit='foobar',
            job_tags='bar,foo'
        )
        job = jt.launch().wait_until_completed()
        job.assert_successful()

        jt.delete()

        relaunched_job = job.relaunch().wait_until_completed()
        relaunched_job.assert_successful()
        assert relaunched_job.limit == 'foobar'
        assert relaunched_job.job_tags == 'bar,foo'

    def test_other_users_cannot_relaunch_orphan_jobs(self, factories, non_superuser):
        jt = factories.v2_job_template()
        jt.set_object_roles(non_superuser, 'admin')

        with self.current_user(non_superuser):
            job = jt.launch().wait_until_completed()
        job.assert_successful()

        jt.delete()

        with self.current_user(non_superuser):
            with pytest.raises(exc.Forbidden):
                job.relaunch()

    def test_relaunch_failed_hosts(self, factories, ansible_version_cmp):
        # In Ansible 2.8, rescued tasks are not considered to be failures
        if ansible_version_cmp("2.8") < 0:
            num_failed_hosts = 3
        else:
            num_failed_hosts = 2

        jt = factories.v2_job_template(playbook='gen_host_status.yml')
        hosts = [factories.v2_host(name=name, inventory=jt.ds.inventory, variables={}) for name in
                 ('1_ok', '2_skipped', '3_changed', '4_failed', '5_ignored', '6_rescued', '7_unreachable')]

        job = jt.launch().wait_until_completed()
        assert not job.is_successful
        assert job.related.relaunch.get().retry_counts.all == 7
        assert job.related.relaunch.get().retry_counts.failed == num_failed_hosts

        hosts = [host.patch(name=name) for host, name in
                 zip(hosts, ('1_failed', '2_failed', '3_failed', '4_ok', '5_failed', '6_ok', '7_ok'))]
        relaunched_job = job.relaunch(payload={'hosts': 'failed'}).wait_until_completed()
        relaunched_job.assert_successful()
        assert relaunched_job.related.relaunch.get().retry_counts.all == num_failed_hosts
        assert relaunched_job.related.relaunch.get().retry_counts.failed == 0

    def test_job_host_summary_status_are_accurate(self, factories, ansible_version_cmp):
        if ansible_version_cmp("2.8") >= 0:
            pytest.skip()
        job_statuses = ['ignored', 'skipped', 'ok', 'changed', 'failed', 'failures', 'rescued', 'skipped']
        jt = factories.v2_job_template(playbook='gen_host_status.yml')
        [factories.v2_host(name=name, inventory=jt.ds.inventory, variables={}) for name in
                 ('1_ok', '2_skipped', '3_changed', '4_failed', '5_ignored', '6_rescued')]
        job = jt.launch().wait_until_completed()
        assert not job.is_successful
        job_host_summaries = job.related.job_host_summaries.get().results
        summary_dict = dict()
        for host in job_host_summaries:
            summary_dict[host['host_name']] = dict()
            for status in job_statuses:
                summary_dict[host['host_name']][status] = host[status]
        assert summary_dict['1_ok'] == {'ignored': 0, 'skipped': 6, 'ok': 1, 'changed': 0, 'failed': False, 'failures': 0, 'rescued': 0}
        assert summary_dict['2_skipped'] == {'ignored': 0, 'skipped': 7, 'ok': 0, 'changed': 0, 'failed': False, 'failures': 0, 'rescued': 0}
        assert summary_dict['3_changed'] == {'ignored': 0, 'skipped': 5, 'ok': 2, 'changed': 1, 'failed': False, 'failures': 0, 'rescued': 0}
        assert summary_dict['4_failed'] == {'ignored': 0, 'skipped': 1, 'ok': 1, 'changed': 0, 'failed': True, 'failures': 1, 'rescued': 0}
        assert summary_dict['5_ignored'] == {'ignored': 1, 'skipped': 5, 'ok': 2, 'changed': 0, 'failed': False, 'failures': 0, 'rescued': 0}
        assert summary_dict['6_rescued'] == {'ignored': 0, 'skipped': 5, 'ok': 2, 'changed': 0, 'failed': False, 'failures': 0, 'rescued': 1}

    def test_password_survey_launched_with_empty_extra_vars(self, factories):
        """Confirms that password surveys with defaults are displayed (and encrypted) when
        job template is launched with empty extra_vars, and those without defaults are not.
        """
        survey = [dict(required=False,
                       question_name="{} - What's the password?".format(i),
                       variable='secret{}'.format(i),
                       type='password') for i in range(10)]
        for i in range(10):
            if i % 2:
                survey[i]['default'] = 'visible'
        jt = factories.job_template()
        jt.add_survey(spec=survey)
        job = jt.launch(dict(extra_vars={}))
        job.wait_until_completed().assert_successful()
        extra_vars = json.loads(job.extra_vars)

        # only half of passwords had default values
        assert len(extra_vars) == 5, "extra_vars found to be undesired length: {0}".format(extra_vars)

        assert all([val == "$encrypted$" for val in extra_vars.values()]), (
               "Undesired values for extra_vars detected: {0}".format(extra_vars))

    def test_survey_defaults_must_meet_length_requirements(self, factories):
        host = factories.v2_host()
        jt = factories.v2_job_template(inventory=host.ds.inventory)
        spec = [dict(required=False, question_name="Text-default too short.",
                     variable='test_var_one', type='text', min=7, default=''),
                dict(required=False, question_name="Text-default too long.",
                     variable='test_var_two', type='text', max=1, default='four'),
                dict(required=False, question_name="Text-passed default with minimum.",
                     variable='test_var_three', type='text', min=0, default='abc'),
                dict(required=False, question_name="Text-passed default with maximum.",
                     variable='test_var_four', type='text', max=7, default='1'),
                dict(required=False, question_name="Text-passed default with compatible minimum and maximum.",
                     variable='test_var_five', type='text', min=1, max=5, default='four'),
                dict(required=False, question_name="Text-default too long.",
                     variable='test_var_six', type='text', min=4, max=4, default='asdfasdf'),
                dict(required=False, question_name="Password-default too short.",
                     variable='test_var_seven', type='password', min=7, default='four'),
                dict(required=False, question_name="Password-default too long.",
                     variable='test_var_eight', type='password', max=1, default='four'),
                dict(required=False, question_name="Password-passed default with minimum.",
                     variable='test_var_nine', type='password', min=1, default='abc'),
                dict(required=False, question_name='Password-passed default with maximum.',
                     variable='test_var_ten', type='password', max=7, default='abc'),
                dict(required=False, question_name="Password-passed default with compatible minimum and maximum.",
                     variable='test_var_eleven', type='password', min=1, max=5, default='four'),
                dict(required=False, question_name="Password-default too long.",
                     variable='test_var_twelve', type='password', min=4, max=4, default='asdfasdf')]
        jt.add_survey(spec=spec)

        job = jt.launch().wait_until_completed()
        job.assert_successful()
        assert json.loads(job.extra_vars) == dict(test_var_three='abc', test_var_four='1', test_var_five='four',
                                                  test_var_nine='$encrypted$', test_var_ten='$encrypted$',
                                                  test_var_eleven='$encrypted$')

    def test_passed_survey_defaults_must_meet_length_requirements(self, factories):
        host = factories.v2_host()
        jt = factories.v2_job_template(inventory=host.ds.inventory)
        spec = [dict(required=False, question_name="Text-default too short.",
                     variable='test_var_one', type='text', min=7, default=''),
                dict(required=False, question_name="Text-default too long.",
                     variable='test_var_two', type='text', max=1, default='four'),
                dict(required=False, question_name="Text-passed default with minimum.",
                     variable='test_var_three', type='text', min=0, default='abc'),
                dict(required=False, question_name="Text-passed default with maximum.",
                     variable='test_var_four', type='text', max=7, default='1'),
                dict(required=False, question_name="Text-passed default with compatible minimum and maximum.",
                     variable='test_var_five', type='text', min=1, max=5, default='four'),
                dict(required=False, question_name="Text-default too long.",
                     variable='test_var_six', type='text', min=4, max=4, default='asdfasdf'),
                dict(required=False, question_name="Password-default too short.",
                     variable='test_var_seven', type='password', min=7, default='four'),
                dict(required=False, question_name="Password-default too long.",
                     variable='test_var_eight', type='password', max=1, default='four'),
                dict(required=False, question_name="Password-passed default with minimum.",
                     variable='test_var_nine', type='password', min=1, default='abc'),
                dict(required=False, question_name='Password-passed default with maximum.',
                     variable='test_var_ten', type='password', max=7, default='abc'),
                dict(required=False, question_name="Password-passed default with compatible minimum and maximum.",
                     variable='test_var_eleven', type='password', min=1, max=5, default='four'),
                dict(required=False, question_name="Password-default too long.",
                     variable='test_var_twelve', type='password', min=4, max=4, default='asdfasdf')]
        jt.add_survey(spec=spec)

        payload = dict(extra_vars=dict(test_var_one='', test_var_two='four', test_var_three='abc',
                                       test_var_four='1', test_var_five='four', test_var_six='asdfasdf',
                                       test_var_seven='$encrypted$', test_var_eight='$encrypted$',
                                       test_var_nine='$encrypted$', test_var_ten='$encrypted$',
                                       test_var_eleven='$encrypted$', test_var_twelve='$encrypted$'))
        with pytest.raises(exc.BadRequest) as e:
            jt.launch(payload)
        assert e.value[1]['variables_needed_to_start'] == \
            ["'test_var_one' value  is too small (length is 0 must be at least 7).",
             "'test_var_two' value four is too large (must be no more than 1).",
             "'test_var_six' value asdfasdf is too large (must be no more than 4)."]

    def test_encrypted_disallowed_as_survey_default_answer(self, factories):
        jt = factories.v2_job_template()
        spec = [dict(required=True, question_name="With $encrypted$ as default.",
                     variable='test', type='password', default='$encrypted$')]

        with pytest.raises(exc.BadRequest) as e:
            jt.add_survey(spec=spec)
        assert e.value[1]['error'] == "$encrypted$ is a reserved keyword, may not be used for new default in position 0."

    @pytest.mark.ansible_integration
    @pytest.mark.mp_group(group="job_with_status_pending", strategy="isolated_serial")
    def test_cancel_pending_job(self, skip_if_cluster, job_with_status_pending):
        """Verify the job->cancel endpoint behaves as expected when canceling a
        pending/queued job
        """
        cancel_pg = job_with_status_pending.get_related('cancel')
        assert cancel_pg.can_cancel, "Unable to cancel job (can_cancel:%s)" % cancel_pg.can_cancel

        # cancel job
        cancel_pg.post()

        # wait for job to complete
        job_with_status_pending = job_with_status_pending.wait_until_completed()

        assert job_with_status_pending.status == 'canceled', \
            "Unexpected job status after cancelling (expected 'canceled') - " \
            "%s" % job_with_status_pending

        # Make sure the ansible-playbook did not start

        # Inspect the job_events and assert that the playbook_on_start
        # event was never received.  If 'playbook_on_start' event appears, then
        # ansible-playbook started, and the job was not cancelled in the
        # 'pending' state.
        job_events = job_with_status_pending.get_related('job_events', event="playbook_on_start")
        assert job_events.count == 0, "The pending job was successfully " \
            "canceled, but a 'playbook_on_start' host_event was received. " \
            "It appears that the job was not cancelled while in pending."

    @pytest.mark.ansible_integration
    def test_cancel_running_job(self, job_with_status_running):
        """Verify the job->cancel endpoint behaves as expected when canceling a
        running job
        """
        cancel_pg = job_with_status_running.get_related('cancel')
        assert cancel_pg.can_cancel, "Unable to cancel job (can_cancel:%s)" % cancel_pg.can_cancel

        # cancel job
        cancel_pg.post()

        # wait for job to complete
        job_with_status_running = job_with_status_running.wait_until_completed()

        assert job_with_status_running.status == 'canceled', \
            "Unexpected job status after cancelling job (expected status: canceled) - %s" % \
            job_with_status_running

        # Make sure the ansible-playbook did not complete

        # First, inspect the job_events and assert that the playbook_on_stats
        # event was never received.  If 'playbook_on_stats' event appears, then
        # ansible-playbook completed, despite the job status being marked as
        # 'canceled'.
        job_events = job_with_status_running.get_related('job_events', event="playbook_on_stats")
        assert job_events.count == 0, "The job was successfully canceled, but a" \
            "'playbook_on_stats' host_event was received.  It appears that the " \
            "ansible-playbook didn't cancel as expected."

        # Second, be sure the standard "PLAY RECAP" is missing from standard
        # output
        assert "PLAY RECAP ************" not in job_with_status_running.result_stdout

    def test_cancel_completed_job(self, job_with_status_completed):
        """Verify the job->cancel endpoint behaves as expected when canceling a
        completed job
        """
        cancel_pg = job_with_status_completed.get_related('cancel')

        # assert not can_cancel
        assert not cancel_pg.can_cancel, \
            "Unexpectedly able to cancel a completed job (can_cancel:%s)" % \
            cancel_pg.can_cancel

        # assert MethodNotAllowed when attempting to cancel
        with pytest.raises(exc.MethodNotAllowed):
            cancel_pg.post()

    def test_jobs_persist_beyond_job_template_deletion(self, job_template):
        """Verify that jobs presist beyond their JT deletion."""
        job = job_template.launch().wait_until_completed()
        job_template.delete()

        # verify that our job persists
        job.get()

    @pytest.mark.parametrize('resource', ['project', 'custom_inventory_source'])
    def test_cascade_delete_update_unified_jobs(self, request, resource):
        """Verify that project and inventory updates get cascade deleted with their UJT deletion."""
        resource = request.getfixturevalue(resource)
        update = resource.update().wait_until_completed()

        # delete unified job template
        if resource.type == 'project':
            resource.delete()
        else:
            resource.related.inventory.delete().wait_until_deleted()

        # verify that update cascade deleted
        with pytest.raises(exc.NotFound):
            update.get()

    def test_delete_running_job_with_orphaned_project(self, factories, user_password):
        """Confirms that JT w/ cross org inventory and orphaned project deletion attempt triggers Forbidden"""
        org = factories.organization()
        operator = factories.user(organization=org)
        org.add_admin(operator)

        orphaned_project = factories.project(organization=None)
        cross_inventory = factories.inventory(organization=factories.organization())
        job_template = factories.job_template(organization=org,
                                              project=orphaned_project,
                                              inventory=cross_inventory)

        job_template.set_object_roles(operator, "execute")
        with self.current_user(operator.username, user_password):
            job = job_template.launch()
            with pytest.raises(exc.Forbidden):
                job.delete()


@pytest.mark.api
@pytest.mark.destructive
class Test_Job_Env(APITest):
    """Verify that credentials are properly passed to playbooks as
    environment variables ('job_env').
    """

    pytestmark = pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')

    def test_job_env_with_cloud_credential(self, job_template_with_cloud_credential):
        """Verify that job_env has the expected cloud_credential variables.

        Note: Tower doesn't set environmental variables for CloudForms and Satellite6.
        """
        # get cloud_credential
        cloud_credential = job_template_with_cloud_credential.get_related('cloud_credential')

        # launch job and assert successful
        job_pg = job_template_with_cloud_credential.launch().wait_until_completed()
        job_pg.assert_successful()

        # assert expected environment variables and their values
        if cloud_credential.kind == 'aws':
            self.has_credentials('cloud', cloud_credential.kind, ['username'])
            expected_env_vars = dict(
                AWS_ACCESS_KEY_ID=self.credentials['cloud'][cloud_credential.kind]['username'],
                AWS_SECRET_ACCESS_KEY='**********'
            )
        elif cloud_credential.kind == 'gce':
            self.has_credentials('cloud', cloud_credential.kind, ['username', 'project'])
            expected_env_vars = dict(
                GCE_EMAIL=self.credentials['cloud'][cloud_credential.kind]['username'],
                GCE_PROJECT=self.credentials['cloud'][cloud_credential.kind]['project'],
                GCE_CREDENTIALS_FILE_PATH=lambda x: re.match(r'^/tmp/awx_\w+/tmp\w+', x)
            )
        elif cloud_credential.kind == 'azure_rm' and azure_type(cloud_credential) == 'azure':
            self.has_credentials('cloud', 'azure', ['subscription_id', 'client_id', 'secret', 'tenant'])
            expected_env_vars = dict(
                AZURE_CLIENT_ID=self.credentials['cloud']['azure']['client_id'],
                AZURE_TENANT=self.credentials['cloud']['azure']['tenant'],
                AZURE_SUBSCRIPTION_ID=self.credentials['cloud']['azure']['subscription_id'],
                AZURE_SECRET='**********',
            )
        elif cloud_credential.kind == 'azure_rm' and azure_type(cloud_credential) == 'azure_ad':
            self.has_credentials('cloud', 'azure_ad', ['subscription_id', 'ad_user', 'password'])
            expected_env_vars = dict(
                AZURE_SUBSCRIPTION_ID=self.credentials['cloud']['azure']['subscription_id'],
                AZURE_AD_USER=self.credentials['cloud']['azure_ad']['ad_user'],
                AZURE_PASSWORD='**********',
            )
        elif cloud_credential.kind == 'vmware':
            self.has_credentials('cloud', cloud_credential.kind, ['username', 'host'])
            expected_env_vars = dict(
                VMWARE_USER=self.credentials['cloud'][cloud_credential.kind]['username'],
                VMWARE_PASSWORD='**********',
                VMWARE_HOST=self.credentials['cloud'][cloud_credential.kind]['host']
            )
        elif cloud_credential.kind == 'openstack':
            if "openstack-v2" in cloud_credential.name:
                self.has_credentials('cloud', 'openstack_v2', ['username', 'host', 'project'])
            elif "openstack-v3" in cloud_credential.name:
                self.has_credentials('cloud', 'openstack_v3', ['username', 'host', 'project', 'domain'])
            else:
                raise ValueError("Unhandled OpenStack credential: %s" % cloud_credential.name)
            expected_env_vars = dict(
                OS_CLIENT_CONFIG_FILE=lambda x: re.match(r'^/tmp/awx_\w+/tmp\w+', x)
            )
        elif cloud_credential.kind in ('cloudforms', 'satellite6'):
            self.has_credentials('cloud', cloud_credential.kind, ['host', 'username', 'password'])
            expected_env_vars = dict()
        else:
            raise ValueError("Unhandled cloud type: %s" % cloud_credential.kind)

        # assert the expected job_env variables are present
        confirm_job_env(job_pg, expected_env_vars)

    def test_job_env_with_network_credential(self, job_template_with_network_credential, expected_net_env_vars):
        """Verify that job_env has the expected network_credential variables."""
        # get cloud_credential
        network_credential = job_template_with_network_credential.get_related('network_credential')

        # launch job and assert successful
        job_pg = job_template_with_network_credential.launch().wait_until_completed()
        job_pg.assert_successful()

        # assert the expected job_env variables are present
        expected_env_vars = expected_net_env_vars(network_credential)
        confirm_job_env(job_pg, expected_env_vars)
