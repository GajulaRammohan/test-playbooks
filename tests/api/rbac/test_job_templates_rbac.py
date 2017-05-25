import pytest
import httplib
import json

import towerkit.exceptions
from tests.lib.helpers.rbac_utils import (
    assert_response_raised,
    check_read_access,
    check_request,
    check_role_association,
    check_user_capabilities
)
from tests.api import Base_Api_Test


@pytest.mark.api
@pytest.mark.ha_tower
@pytest.mark.rbac
@pytest.mark.skip_selenium
class Test_Job_Template_RBAC(Base_Api_Test):

    pytestmark = pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')

    def test_unprivileged_user(self, factories):
        """An unprivileged user/team should not be able to:
        * Get the JT details page
        * Get all of the JT get_related pages
        * Launch the JT
        * Edit the JT
        * Delete the JT
        """
        job_template = factories.job_template()
        user = factories.user()

        with self.current_user(username=user.username, password=user.password):
            # check GET as test user
            check_read_access(job_template, unprivileged=True)

            # check JT launch
            with pytest.raises(towerkit.exceptions.Forbidden):
                job_template.related.launch.post()

            # check put/patch/delete
            assert_response_raised(job_template, httplib.FORBIDDEN)

    @pytest.mark.parametrize("agent", ["user", "team"])
    def test_admin_role(self, factories, set_test_roles, agent):
        """A user/team with JT 'admin' should be able to:
        * Get the JT details page
        * Get all of the JT get_related pages
        * Edit the JT
        * Delete the JT
        """
        job_template = factories.job_template()
        user = factories.user()

        # give agent admin_role
        set_test_roles(user, job_template, agent, "admin")

        with self.current_user(username=user.username, password=user.password):
            # check GET as test user
            check_read_access(job_template, ["credential", "inventory", "project"])

            # check put/patch/delete
            assert_response_raised(job_template.get(), httplib.OK)

    @pytest.mark.parametrize("agent", ["user", "team"])
    def test_execute_role(self, factories, set_test_roles, agent):
        """A user/team with JT 'execute' should be able to:
        * Get the JT details page
        * Get all of the JT get_related pages
        A user/team with JT 'execute' should not be able to:
        * Edit the JT
        * Delete the JT
        """
        job_template = factories.job_template()
        user = factories.user()

        # give agent execute_role
        set_test_roles(user, job_template, agent, "execute")

        with self.current_user(username=user.username, password=user.password):
            # check GET as test user
            check_read_access(job_template, ["credential", "inventory", "project"])

            # check put/patch/delete
            assert_response_raised(job_template, httplib.FORBIDDEN)

    @pytest.mark.parametrize("agent", ["user", "team"])
    def test_read_role(self, factories, set_test_roles, agent):
        """A user/team with JT 'admin' should be able to:
        * Get the JT details page
        * Get all of the JT get_related pages
        A user/team with JT 'admin' should not be able to:
        * Edit the JT
        * Delete the JT
        """
        job_template = factories.job_template()
        user = factories.user()

        # give agent read_role
        set_test_roles(user, job_template, agent, "read")

        with self.current_user(username=user.username, password=user.password):
            # check GET as test user
            check_read_access(job_template, ["credential", "inventory", "project"])

            # check put/patch/delete
            assert_response_raised(job_template, httplib.FORBIDDEN)

    @pytest.mark.parametrize('role', ['admin', 'execute', 'read'])
    def test_user_capabilities(self, factories, api_job_templates_pg, role):
        """Test user_capabilities given each job_template role."""
        job_template = factories.job_template()
        user = factories.user()

        job_template.set_object_roles(user, role)

        with self.current_user(username=user.username, password=user.password):
            check_user_capabilities(job_template.get(), role)
            check_user_capabilities(api_job_templates_pg.get(id=job_template.id).results.pop(), role)

    def test_autopopulated_admin_role_with_job_template_creator(self, request, factories, api_job_templates_pg):
        """Verify that job template creators are added to the admin role of the
        created job template.
        """
        # make test user
        user = factories.user()
        # generate job template test payload
        jt_payload = factories.job_template.payload()
        # set user resource role associations
        jt_payload.ds.inventory.ds.organization.set_object_roles(user, 'admin')
        for name in ('credential', 'project', 'inventory'):
            jt_payload.ds[name].set_object_roles(user, 'use')
        # create a job template as the test user
        with self.current_user(username=user.username, password=user.password):
            job_template = api_job_templates_pg.post(jt_payload)
            request.addfinalizer(job_template.silent_cleanup)
        # verify succesful job_template admin role association
        check_role_association(user, job_template, 'admin')

    @pytest.mark.parametrize('payload_resource_roles, response_codes', [
        (
            {'credential': ['read'], 'inventory': ['use'], 'project': ['use']},
            {'PATCH': httplib.FORBIDDEN, 'PUT': httplib.FORBIDDEN}
        ),
        (
            {'credential': ['use'], 'inventory': ['read'], 'project': ['use']},
            {'PATCH': httplib.FORBIDDEN, 'PUT': httplib.FORBIDDEN}
        ),
        (
            {'credential': ['use'], 'inventory': ['use'], 'project': ['read']},
            {'PATCH': httplib.FORBIDDEN, 'PUT': httplib.FORBIDDEN}
        ),
        (
            {'credential': ['use'], 'inventory': ['use'], 'project': ['use']},
            {'PATCH': httplib.OK, 'PUT': httplib.OK}
        ),
    ])
    def test_job_template_change_request_without_usage_role_returns_code_403(self,
            factories, payload_resource_roles, response_codes):
        """Verify that a user cannot change the related project, inventory, or
        credential of a job template unless they have usage permissions on all
        three resources and are admins of the job template
        """
        user = factories.user()
        organization = factories.organization()
        job_template = factories.job_template(inventory=(True, dict(organization=organization)))
        organization.set_object_roles(user, 'member')
        job_template.set_object_roles(user, 'admin')
        # generate test request payload

        jt_payload = factories.job_template.payload(inventory=job_template.ds.inventory,
                                                    credential=job_template.ds.credential)
        # assign test permissions
        for name, roles in payload_resource_roles.iteritems():
            jt_payload.ds[name].set_object_roles(user, *roles)
        # check access
        with self.current_user(username=user.username, password=user.password):
            for method, code in response_codes.iteritems():
                check_request(job_template, method, code, data=jt_payload)

    def test_job_template_post_request_without_network_credential_access(self,
            factories, api_job_templates_pg):
        """Verify that job_template post requests with network credentials in
        the payload are only permitted if the user making the request has usage
        permission for the network credential.
        """
        # set user resource role associations
        jt_payload = factories.job_template.payload()
        organization = jt_payload.ds.inventory.ds.organization
        user = factories.user(organization=organization)
        for name in ('credential', 'project', 'inventory'):
            jt_payload.ds[name].set_object_roles(user, 'use')
        # make network credential and add it to payload
        network_credential = factories.credential(kind='net', organization=organization)
        jt_payload.network_credential = network_credential.id
        # check POST response code with network credential read permissions
        network_credential.set_object_roles(user, 'read')
        with self.current_user(user.username, password=user.password):
            check_request(api_job_templates_pg, 'POST', httplib.FORBIDDEN, jt_payload)
        # add network credential usage role permissions to test user
        network_credential.set_object_roles(user, 'use')
        # verify that the POST request is now permitted
        with self.current_user(user.username, password=user.password):
            check_request(api_job_templates_pg, 'POST', httplib.CREATED, jt_payload)

    @pytest.mark.parametrize('role', ['admin', 'execute', 'read'])
    def test_launch_job(self, factories, role):
        """Tests ability to launch a job."""
        ALLOWED_ROLES = ['admin', 'execute']
        REJECTED_ROLES = ['read']

        job_template = factories.job_template()
        user = factories.user()

        job_template.set_object_roles(user, role)

        with self.current_user(username=user.username, password=user.password):
            if role in ALLOWED_ROLES:
                job = job_template.launch().wait_until_completed()
                assert job.is_successful, "Job unsuccessful - %s." % job
            elif role in REJECTED_ROLES:
                with pytest.raises(towerkit.exceptions.Forbidden):
                    job_template.launch()
            else:
                raise ValueError("Received unhandled job_template role.")

    def test_launch_as_auditor(self, factories):
        """Confirms that a system auditor cannot launch job templates"""
        jt = factories.job_template()
        user = factories.user()
        user.is_system_auditor = True
        with self.current_user(user.username, user.password):
            with pytest.raises(towerkit.exceptions.Forbidden):
                jt.launch().wait_until_completed()

    @pytest.mark.parametrize('role', ['admin', 'execute', 'read'])
    def test_relaunch_job(self, factories, role):
        """Tests ability to relaunch a job."""
        ALLOWED_ROLES = ['admin', 'execute']
        REJECTED_ROLES = ['read']

        job_template = factories.job_template()
        user = factories.user()

        job_template.set_object_roles(user, role)

        job = job_template.launch().wait_until_completed()
        assert job.is_successful, "Job unsuccessful - %s." % job

        with self.current_user(username=user.username, password=user.password):
            if role in ALLOWED_ROLES:
                relaunched_job = job.relaunch().wait_until_completed()
                assert relaunched_job.is_successful, "Job unsuccessful - %s." % job
            elif role in REJECTED_ROLES:
                with pytest.raises(towerkit.exceptions.Forbidden):
                    job.relaunch()
            else:
                raise ValueError("Received unhandled job_template role.")

    def test_relaunch_with_ask_inventory(self, factories, job_template):
        """Tests relaunch RBAC when ask_inventory_on_launch is true."""
        # FIXME: update for factories when towerkit-210 gets resolved
        job_template.ds.inventory.delete()
        job_template.patch(ask_inventory_on_launch=True)

        credential = job_template.ds.credential
        inventory = factories.inventory()
        user1, user2 = factories.user(), factories.user()

        # set test permissions
        job_template.set_object_roles(user1, 'execute')
        inventory.set_object_roles(user1, 'use')
        credential.set_object_roles(user1, 'use')
        job_template.set_object_roles(user2, 'execute')

        # launch job as user1
        with self.current_user(username=user1.username, password=user1.password):
            payload = dict(inventory=inventory.id)
            job = job_template.launch(payload).wait_until_completed()

        # relaunch as user2 should raise 403
        with self.current_user(username=user2.username, password=user2.password):
            with pytest.raises(towerkit.exceptions.Forbidden):
                job.relaunch()

    def test_relaunch_with_ask_credential(self, factories, job_template_no_credential):
        """Tests relaunch RBAC when ask_credential_on_launch is true."""
        job_template_no_credential.patch(ask_credential_on_launch=True)

        credential = factories.credential()
        user1 = factories.user(organization=credential.ds.organization)
        user2 = factories.user()

        # set test permissions
        job_template_no_credential.set_object_roles(user1, 'execute')
        credential.set_object_roles(user1, 'use')
        job_template_no_credential.set_object_roles(user2, 'execute')

        # launch job as user1
        with self.current_user(username=user1.username, password=user1.password):
            payload = dict(credential=credential.id)
            job = job_template_no_credential.launch(payload).wait_until_completed()

        # relaunch as user2 should raise 403
        with self.current_user(username=user2.username, password=user2.password):
            with pytest.raises(towerkit.exceptions.Forbidden):
                job.relaunch()

    def test_relaunch_job_as_auditor(self, factories, job_with_status_completed):
        """Confirms that a system auditor cannot relaunch a job"""
        user = factories.user()
        user.is_system_auditor = True
        with self.current_user(user.username, user.password):
            with pytest.raises(towerkit.exceptions.Forbidden):
                job_with_status_completed.relaunch().wait_until_completed()

    @pytest.mark.parametrize('role', ['admin', 'execute', 'read'])
    def test_schedule_job(self, factories, role):
        """Tests ability to schedule a job."""
        ALLOWED_ROLES = ['admin', 'execute']
        REJECTED_ROLES = ['read']

        job_template = factories.job_template()
        user = factories.user()

        job_template.set_object_roles(user, role)

        with self.current_user(username=user.username, password=user.password):
            if role in ALLOWED_ROLES:
                schedule = job_template.add_schedule()
                assert_response_raised(schedule, methods=('get', 'put', 'patch', 'delete'))
            elif role in REJECTED_ROLES:
                with pytest.raises(towerkit.exceptions.Forbidden):
                    job_template.add_schedule()
            else:
                raise ValueError("Received unhandled job_template role.")

    @pytest.mark.parametrize('role', ['admin', 'execute', 'read'])
    def test_cancel_job(self, factories, role):
        """Tests job cancellation. JT admins can cancel other people's jobs."""
        ALLOWED_ROLES = ['admin']
        REJECTED_ROLES = ['execute', 'read']

        job_template = factories.job_template(playbook='sleep.yml', extra_vars=json.dumps(dict(sleep_interval=10)))
        user = factories.user()

        job_template.set_object_roles(user, role)

        # launch job_template
        job = job_template.launch()

        with self.current_user(username=user.username, password=user.password):
            if role in ALLOWED_ROLES:
                job.cancel()
            elif role in REJECTED_ROLES:
                with pytest.raises(towerkit.exceptions.Forbidden):
                    job.cancel()
                # wait for job to finish to ensure clean teardown
                job.wait_until_completed()
            else:
                raise ValueError("Received unhandled job_template role.")

    def test_delete_job_as_org_admin(self, factories):
        """Create a run and a scan JT and an org_admin for each of these JTs. Then check
        that each org_admin may only delete his org's job.
        Note: job deletion is organization scoped. A run JT's project determines its
        organization and a scan JT's inventory determines its organization.
        """
        # create two JTs
        run_job_template = factories.job_template()
        scan_job_template = factories.job_template(job_type="scan", project=None)

        # sanity check
        run_jt_org = run_job_template.ds.project.ds.organization
        scan_jt_org = scan_job_template.ds.inventory.ds.organization
        assert run_jt_org.id != scan_jt_org.id, "Test JTs unexpectedly in the same organization."

        # create org_admins
        org_admin1 = factories.user(organization=run_jt_org)
        org_admin2 = factories.user(organization=scan_jt_org)
        run_jt_org.set_object_roles(org_admin1, 'admin')
        scan_jt_org.set_object_roles(org_admin2, 'admin')

        # launch JTs
        run_job = run_job_template.launch()
        scan_job = scan_job_template.launch()

        # assert that each org_admin cannot delete other organization's job
        with self.current_user(username=org_admin1.username, password=org_admin1.password):
            with pytest.raises(towerkit.exceptions.Forbidden):
                scan_job.delete()
        with self.current_user(username=org_admin2.username, password=org_admin2.password):
            with pytest.raises(towerkit.exceptions.Forbidden):
                run_job.delete()

        # assert that each org_admin can delete his own organization's job
        with self.current_user(username=org_admin1.username, password=org_admin1.password):
            run_job.delete()
        with self.current_user(username=org_admin2.username, password=org_admin2.password):
            scan_job.delete()

    def test_delete_job_as_org_user(self, factories):
        """Tests ability to delete a job as a privileged org_user."""
        job_template = factories.job_template()
        user = factories.user()

        job_template.set_object_roles(user, 'admin')

        # launch job_template
        job = job_template.launch().wait_until_completed()

        with self.current_user(username=user.username, password=user.password):
            with pytest.raises(towerkit.exceptions.Forbidden):
                job.delete()

    @pytest.mark.parametrize('role', ['admin', 'execute', 'read'])
    def test_job_user_capabilities(self, factories, api_jobs_pg, role):
        """Test user_capabilities given each JT role on spawned jobs."""
        job_template = factories.job_template()
        user = factories.user()

        job_template.set_object_roles(user, role)

        # launch job_template
        job = job_template.launch().wait_until_completed()

        with self.current_user(username=user.username, password=user.password):
            check_user_capabilities(job.get(), role)
            check_user_capabilities(api_jobs_pg.get(id=job.id).results.pop(), role)
