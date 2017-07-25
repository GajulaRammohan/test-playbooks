import logging
import re

import pytest
import towerkit
from towerkit.utils import poll_until

from tests.api import Base_Api_Test
from tests.lib.helpers.workflow_utils import (WorkflowTree, WorkflowTreeMapper)

# Job results
# [x] Single node success
# [x] Single failing node
# [x] Node fails, triggers successful node
# [ ] Two branches, one node succeeds, other fails
# [ ] Individual job encounters error
# [ ] Workflow job encounters error
# [ ] Workflow job interrupted (e.g. by restarting tower)

# Job runs
# [x] Node triggers success/failure/always nodes when appropriate
# [x] Workflow includes multiple nodes that point to same unified job template
# [ ] Running concurrent workflows
# [ ] Changing job node while workflow is running
# [ ] Changing job template while workflow is running (change playbook, add survey, delete extra var..)
# [ ] Kicking off workflow when a job included in workflow has already been kicked off (as single job)
# [ ] Confirm including job template in workflow doesn't impair to run job template outside workflows
# [ ] Two workflows contain same node. Run both workflows at same time. Any collisions? (e.g. w/ artifacts)
# [ ] Using any misc settings (e.g. forks)

# Cancel
# [x] Cancelling individual job in workflow
# [x] Cancelling workflow

# Notifications
# [ ] For workflow's various states

# Timeouts
# [ ] On node
# [ ] On workflow

# Schedules
# [ ]

# Negative testing
# [ ] (-) No nodes
# [ ] (-) Delete unified job template used by node, run job
# [ ] (-) Delete unified job template used by node, while workflow in progress
# [ ] (-) Should not be able to re-run a job that was a part of a larger workflow job
# [ ] Delete a job that was part of a larger workflow job?
# [ ] (-) Delete workflow job while in progress
# [ ] Add new nodes to workflow while workflow is in progress

# Extra vars / Surveys / Prompting
# [ ] Workflow survey with non-default variable
# [ ] Job template prompts for credential, inventory, project, ..
# [ ] Create workflow, update node job template to require additional variable (using prompting, surveys)
# [ ] Variable precedence testing

# Artifacts (break out into separate test module?)
# [ ] Artifacts cumulative?
# [ ] Sensitive artifacts not exposed

# Workflows and HA
# [ ] Project update during workflow job, does project get copied over to other nodes (race condition?).
# [ ] (Similiar to above) Inventory updates lead to race condition?
# [ ] (-) Workflow running, node brought down

# Workflow job nodes
#

# Activity Stream
#

# Deleting
# [ ] Deleting workflow job (possible?)
# [ ] Delete workflow job template, confirm workflow job (and regular jobs triggered as well) deleted
# [ ] Orphaned workflow jobs

log = logging.getLogger(__name__)


@pytest.mark.api
@pytest.mark.skip_selenium
@pytest.mark.destructive
class Test_Workflow_Jobs(Base_Api_Test):

    pytestmark = pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')

    def test_inventory_source_correctly_referenced_in_related_job_endpoint(self, factories):
        """Confirms that inventory sources are treated as unified job templates in addition to confirming
        related workflow job nodes of inventory update types have correct url
        """
        group = factories.group()
        inv_script = factories.inventory_script()
        inv_source = group.related.inventory_source.patch(source_script=inv_script.id)
        wfjt = factories.workflow_job_template()
        factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=inv_source)
        wfj = wfjt.launch().wait_until_completed()
        wfjn = wfj.related.workflow_nodes.get().results.pop()
        assert('inventory_updates' in wfjn.related.job)  # confirm that it's not linked as a job
        assert(inv_source.related.inventory_updates.get().results.pop().endpoint == wfjn.related.job.get().endpoint)

    # Basic tests of workflow jobs

    @pytest.mark.ansible_integration
    def test_workflow_job_single_node_success(self, factories):
        """Workflow with single node with successful job template.
        Expect workflow job to be 'successful', job to be 'successful'
        """
        wfjt = factories.workflow_job_template()
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory)
        factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt)
        wf_job = wfjt.launch().wait_until_completed()
        assert wf_job.is_successful, "Workflow job {} unsuccessful".format(wfjt.id)

        # Get job in node
        wfjns = wf_job.related.workflow_nodes.get().results
        assert len(wfjns) == 1, "Expected one workflow job node, found {}".format(len(wfjns))
        wfjn = wfjns.pop()
        job = wfjn.get_related('job')
        assert job.is_successful, "Job {} unsuccessful".format(job.id)

        # Confirm WFJ correctly references job
        assert re.match(towerkit.resources.v1_job, wfjn.related.job)
        assert wfjn.get_related('job').endpoint == jt.get().get_related('last_job').endpoint

    @pytest.mark.ansible_integration
    def test_workflow_job_single_node_failure(self, factories):
        """Workflow with single node with failing job template.
        Expect workflow job to be 'successful', job to be 'failure'
        """
        wfjt = factories.workflow_job_template()
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory, playbook='fail_unless.yml')
        factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt)
        wf_job = wfjt.launch().wait_until_completed()
        assert wf_job.is_successful, "Workflow job {} unsuccessful".format(wfjt.id)

        # Get job in node
        wfjns = wf_job.related.workflow_nodes.get().results
        assert len(wfjns) == 1, "Expected one workflow job node, found {}".format(len(wfjns))
        job = wfjns.pop().get_related('job')
        assert not job.is_successful, "Job {} successful".format(job.id)

    @pytest.mark.ansible_integration
    def test_workflow_job_trigger_conditions(self, factories, api_workflow_job_nodes_pg):
        """Confirm that workflow with all possible triggering scenarios executes jobs appropriately.

        Workflow:                        Should run?
         - n1+                           Yes
          - (always) n2                    Yes
         - n3-                           Yes
          - (always) n4                    Yes
          - (always) n5*                   Yes
         - n6+                           Yes
          - (success) n7                   Yes
          - (failure) n8                   No
          - (failure) n9*                  No
         - n10-                          Yes
          - (success) n11                  No
          - (failure) n12                  Yes

        + -> node with passing job
        - -> node with failing job

        * -> Node not essential to test, added so that there could be a unique mapping (i.e. homomorphism) between
             the WFJT's nodes and the WFJ's nodes.
        """
        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory, allow_simultaneous=True)
        failing_jt = factories.job_template(inventory=host.ds.inventory, playbook='fail_unless.yml', allow_simultaneous=True)

        wfjt = factories.workflow_job_template()
        node_payload = dict(unified_job_template=jt.id)
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt)
        n2 = n1.related.always_nodes.post(node_payload)

        n3 = factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=failing_jt)
        n4 = n3.related.always_nodes.post(node_payload)
        n5 = n3.related.always_nodes.post(node_payload)

        n6 = factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt)
        n7 = n6.related.success_nodes.post(node_payload)
        n8 = n6.related.failure_nodes.post(node_payload)
        n9 = n6.related.failure_nodes.post(node_payload)

        n10 = factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=failing_jt)
        n11 = n10.related.success_nodes.post(node_payload)
        n12 = n10.related.failure_nodes.post(node_payload)

        wfj = wfjt.launch().wait_until_completed()
        assert wfj.is_successful, "Workflow job {} unsuccessful".format(wfjt.id)

        # Map nodes to job nodes
        tree = WorkflowTree(wfjt)
        job_tree = WorkflowTree(wfj)
        mapping = WorkflowTreeMapper(tree, job_tree).map()
        assert mapping, "Failed to map WFJT to WFJ.\n\nWFJT:\n{0}\n\nWFJ:\n{1}".format(tree, job_tree)

        # Confirm only expected jobs ran
        should_run_ids = [str(mapping[node.id]) for node in [n1, n2, n3, n4, n5, n6, n7, n10, n12]]
        should_run_nodes = api_workflow_job_nodes_pg.get(id__in=','.join(should_run_ids)).results
        assert all([node.job for node in should_run_nodes]), \
            "Found node(s) missing job: {0}".format(node for node in should_run_nodes if not node.job)
        should_not_run_ids = [str(mapping[node.id]) for node in [n8, n9, n11]]
        should_not_run_nodes = api_workflow_job_nodes_pg.get(id__in=','.join(should_not_run_ids)).results
        assert not any([node.job for node in should_not_run_nodes]), \
            "Found node(s) with job: {0}".format(node for node in should_not_run_nodes if node.job)

    def test_workflow_job_with_project_update(self, factories):
        """Confirms that workflow job can include project updates."""
        project = factories.project()
        wfjt = factories.workflow_job_template()
        factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=project)
        wfj = wfjt.launch().wait_until_completed()
        wfjn = wfj.related.workflow_nodes.get().results.pop()
        assert re.match(towerkit.resources.v1_project_update, wfjn.related.job)
        assert wfjn.get_related('job').endpoint == project.get().get_related('last_job').endpoint

    # Canceling jobs

    def test_cancel_workflow_job(self, factories, api_jobs_pg):
        """Confirm that cancelling a workflow job cancels spawned jobs."""
        # Build workflow
        host = factories.host()
        jt_sleep = factories.job_template(inventory=host.ds.inventory, playbook='sleep.yml')  # Longer-running job
        jt_sleep.extra_vars = '{"sleep_interval": 20}'
        wfjt = factories.workflow_job_template()
        factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt_sleep)

        # Run workflow
        wfj = wfjt.launch()

        # Wait for workflow job to spawn job
        job_nodes = wfj.get_related('workflow_nodes')
        assert len(job_nodes.results) == 1, "Only expecting one job node, found:\n\n{0}".format(job_nodes)
        job_node = job_nodes.results.pop()
        job_node.wait_for_job(timeout=60)  # Job does not exist until kicked off by workflow
        job = job_node.get_related('job')

        # Wait for spawned job to enter running state
        job.wait_until_status('running')

        # ..then cancel workflow job
        wfj.cancel()
        poll_until(lambda: getattr(wfj.get(), 'status') == 'canceled', timeout=3 * 60)

        # Confirm job spawned by workflow job was canceled
        poll_until(lambda: getattr(job.get(), 'status') == 'canceled', timeout=60)

    def test_cancel_job_spawned_by_workflow_job(self, factories):
        """Cancel job spawned by workflow job. Confirm workflow job finishes and is marked successful.

        Workflow:
         n1     <--- cancelled
        """
        host = factories.host()
        jt_sleep = factories.job_template(inventory=host.ds.inventory, playbook='sleep.yml', extra_vars='{"sleep_interval": 20}',
                                          allow_simultaneous=True)  # Longer-running job

        # Build workflow
        wfjt = factories.workflow_job_template()
        factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt_sleep)

        # Run workflow
        wfj = wfjt.launch()

        # Get job node
        job_nodes = wfj.related.workflow_nodes.get().results
        assert len(job_nodes) == 1, 'Expected workflow job to have single node, found:\n\n{0}'.format(job_nodes)
        job_node = job_nodes[0]

        # Wait for node's job to be created
        job_node.wait_for_job(timeout=60)
        assert getattr(job_node, 'job', None), 'Failed to find job listed on node {}'.format(job_node)

        # Cancel job
        job = job_node.related.job.get()
        job.cancel()

        # Confirm job cancelled
        poll_until(lambda: getattr(job.get(), 'status') == 'canceled', timeout=60)

        # Confirm WF job success
        poll_until(lambda: getattr(wfj.get(), 'status') == 'successful', timeout=3 * 60)

    def test_cancel_job_in_workflow_with_downstream_jobs(self, factories, api_jobs_pg):
        """Cancel job spawned by workflow job. Confirm jobs downstream from cancelled job
        are not triggered, but rest of workflow continues to execute.

        Workflow:
         n1                 <--- canceled
          - (success) n2
          - (failure) n3
         n4
          - (always) n5

        Expect:
         - Nodes downstream from n1 (includes n2, n3) should not run.
         - Rest of workflow (includes n4, n5) should run to completion.
        """
        # Create jobs for workflow
        # Note: Both root jobs sleep so that (1) there's time to cancel n1 and (2) n4 does not finish before n1 is
        # canceled. We need n4 to still be running when n1 is cancelled so that we can verify that downstream jobs (n5)
        # are triggered *after* n1 is canceled.

        host = factories.host()
        jt = factories.job_template(inventory=host.ds.inventory)                            # Default job template for all nodes
        jt_sleep = factories.job_template(inventory=host.ds.inventory, playbook='sleep.yml', extra_vars='{"sleep_interval": 20}',
                                          allow_simultaneous=True)  # Longer-running job

        # Build workflow
        wfjt = factories.workflow_job_template()
        node_payload = dict(unified_job_template=jt.id)
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt_sleep)
        n2 = n1.related.success_nodes.post(node_payload)
        n3 = n1.related.failure_nodes.post(node_payload)
        n4 = factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt_sleep)
        n5 = n4.related.always_nodes.post(node_payload)

        # Run workflow
        wfj = wfjt.launch()

        # Get mapping
        # Note: When a workflow job is launched, it immediately creates one WFJ node for every WFJT node
        # in the WFJT (even if that WFJ node's job is never launched). This allows us to create a mapping,
        # even when only the jobs for the root nodes are running. (Otherwise, there would be two possible
        # mappings and it wouldn't be clear which job we should cancel).
        mapping = WorkflowTreeMapper(WorkflowTree(wfjt), WorkflowTree(wfj)).map()
        error = ('Expected Workflow Job to have same tree structure as Workflow Job Template.\n\n'
                 'Workflow Job Template:\n\n{0}\n\nWorkflow Job:\n\n{1}').format(WorkflowTree(wfjt), WorkflowTree(wfj))
        assert mapping, error

        n1_job_node = wfj.related.workflow_nodes.get(id=mapping[n1.id]).results.pop()
        n2_job_node = wfj.related.workflow_nodes.get(id=mapping[n2.id]).results.pop()
        n3_job_node = wfj.related.workflow_nodes.get(id=mapping[n3.id]).results.pop()
        n4_job_node = wfj.related.workflow_nodes.get(id=mapping[n4.id]).results.pop()
        n5_job_node = wfj.related.workflow_nodes.get(id=mapping[n5.id]).results.pop()

        # Cancel job spawned by job node n1
        n1_job_node.wait_for_job(timeout=60)  # Job does not exist until kicked off by workflow
        assert getattr(n1_job_node, 'job', None), 'Failed to find job for node {}'.format(n1_job_node)
        n1_job = n1_job_node.related.job.get()
        n1_job.cancel()

        poll_until(lambda: getattr(n1_job.get(), 'status') == 'canceled', timeout=60)

        # Confirm workflow job completes successfully
        poll_until(lambda: getattr(wfj.get(), 'status') == 'successful', timeout=3 * 60)

        # Confirm remaining jobs in workflow completed successfully
        for job_node in (n4_job_node, n5_job_node):
            job_node.get()
            assert getattr(job_node, 'job', None), 'Failed to find job listed on node {}'.format(job_node)
            assert job_node.get_related('job').status == 'successful'

        # Confirm job downstream from cancelled job never triggered
        for job_node in (n2_job_node, n3_job_node):
            job_node.get()
            assert not getattr(job_node, 'job', None), \
                'Found job listed on node {} (even though parent job node cancelled)'.format(job_node)
