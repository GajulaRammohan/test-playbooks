import pytest
import logging
import json

from towerkit.exceptions import BadRequest, NotFound

from tests.api import APITest
from tests.lib.helpers.workflow_utils import WorkflowTree

log = logging.getLogger(__name__)

# Variations in structure
# [x] Single node
# [x] Multiple root nodes
# [x] Node Depth > 1
# [x] (-) Circular graph
# [ ] Can add node by (a) citing WFJT during node creation, (b) patching node w/ WFJT, (c) posting new node on /workflow_job_templates/\d+/workflow_nodes/

# Copy
# [ ]

# Labels
# [ ]

# Notifications
# [ ] On workflow job template
# [ ] On regular jobs

# Tags / Limits
# [ ]

# Extra vars
# [ ]

# Deleting
# [x] Delete workflow with single node
# [x] Delete intermediate node (with node(s) before/after)
# [x] Delete leaf node
# [x] Deleting root node when depth > 1


@pytest.mark.api
@pytest.mark.destructive
@pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')
class Test_Workflow_Job_Templates(APITest):

    # Graph Topology Validation
    # Graphs should not (1) converge (2) contain cycles or
    # (3) trigger the same node in both always_nodes and {success,failure}_nodes

    def test_converging_nodes(self, factories):
        """Confirms that two nodes cannot trigger the same node"""
        wfjt = factories.workflow_job_template()
        # Create two top-level nodes
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt)
        jt = n1.related.unified_job_template.get()  # Reuse job template from first node
        n2 = factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt)

        # Create third node. Have each root node trigger third node.
        n3 = n1.related.always_nodes.post(dict(unified_job_template=jt.id))
        for condition in ('always', 'success', 'failure'):
            with pytest.raises(BadRequest) as exception:
                n2.get_related(condition + '_nodes').post(dict(id=n3.id))
            assert 'Multiple parent relationship not allowed.' in str(exception.value)

            # Confirm nodes were not linked
            triggered_nodes = n2.get_related(condition + '_nodes').results
            assert not len(triggered_nodes), \
                'Found nodes listed, expected none. (Creates converging path in workflow):\n{0}'.format(triggered_nodes)

    def test_workflow_workflow_node(self, factories):
        """Tests successful use of workflows in workflows"""
        wfjt_outer = factories.workflow_job_template(
            extra_vars={'outer_var': 'foo'}
        )
        wfjt_inner = factories.workflow_job_template(
            extra_vars={'inner_var': 'bar'},
            ask_variables_on_launch=True
        )
        jt = factories.job_template()
        factories.workflow_job_template_node(
            workflow_job_template=wfjt_inner,
            unified_job_template=jt
        )
        node = factories.workflow_job_template_node(workflow_job_template=wfjt_outer)
        node.unified_job_template = wfjt_inner.id
        # HACK: unified_job_template does not work with the dependency store

        wfj_outer = wfjt_outer.launch()
        node = wfj_outer.get_related('workflow_nodes').results.pop().wait_for_job()
        wfj_inner = node.get_related('job')
        wfj_inner.wait_until_completed()
        assert wfj_inner.type == 'workflow_job'
        assert wfj_inner.workflow_job_template == wfjt_inner.id
        assert wfj_inner.status == 'successful'
        assert json.loads(wfj_inner.extra_vars) == {'inner_var': 'bar', 'outer_var': 'foo'}

        # check contents of inner workflow
        inner_nodes = wfj_inner.get_related('workflow_nodes')
        assert inner_nodes.count == 1
        jt_node = inner_nodes.results.pop()
        assert jt_node.job  # inner workflow job is finished, so this must have spawned by now
        jt_job = jt_node.get_related('job')
        assert jt_job.job_template == jt.id
        assert json.loads(jt_job.extra_vars) == {'inner_var': 'bar', 'outer_var': 'foo'}

    def test_workflow_workflow_node_rejected_prompts(self, factories):
        # TODO: update to include prompted inventory when branches merge
        wfjt_outer = factories.workflow_job_template(
            extra_vars={'outer_var': 'foo'}  # inner WFJT does not prompt, should not use these
        )
        wfjt_inner = factories.workflow_job_template(
            extra_vars={'inner_var': 'bar'}
        )
        node = factories.workflow_job_template_node(workflow_job_template=wfjt_outer)
        node.unified_job_template = wfjt_inner.id

        wfj = wfjt_outer.launch()
        node = wfj.get_related('workflow_nodes').results.pop().wait_for_job()
        job = node.get_related('job')
        assert job.type == 'workflow_job'
        assert job.workflow_job_template == wfjt_inner.id
        assert json.loads(job.extra_vars) == {'inner_var': 'bar'}

    def test_workflow_workflow_node_recursion_error(self, factories):
        wfjt = factories.workflow_job_template()
        node = factories.workflow_job_template_node(workflow_job_template=wfjt)
        node.unified_job_template = wfjt.id  # uh oh

        wfj = wfjt.launch()
        node = wfj.get_related('workflow_nodes').results.pop().wait_for_job()
        job = node.get_related('job')
        assert job.type == 'workflow_job'
        assert job.workflow_job_template == wfjt.id
        assert job.status == 'failed'
        assert job.job_explanation.startswith(
            'Workflow Job spawned from workflow could not start because it would result in recursion'
        )

    def test_single_node_references_itself(self, factories):
        """Confirms that a node cannot trigger itself"""
        wfjt = factories.workflow_job_template()
        n = factories.workflow_job_template_node(workflow_job_template=wfjt)
        for condition in ('always', 'success', 'failure'):
            with pytest.raises(BadRequest) as exception:
                n.get_related(condition + '_nodes').post(dict(id=n.id))
            assert 'Cycle detected.' in str(exception.value)

            # Confirm node not linked to itself
            triggered_nodes = n.get_related(condition + '_nodes').results
            assert not len(triggered_nodes), \
                'Found nodes listed, expected none. (Creates cycle in workflow):\n{0}'.format(triggered_nodes)

    def test_cyclic_graph(self, factories):
        """Confirms that a graph cannot contain a cycle"""
        # Create two nodes. First node triggers second node.
        wfjt = factories.workflow_job_template()
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt)
        jt = n1.related.unified_job_template.get()  # Reuse job template from first node
        n2 = n1.related.always_nodes.post(dict(unified_job_template=jt.id))

        # Second node triggers the first (creates cycle)
        for condition in ('always', 'success', 'failure'):
            with pytest.raises(BadRequest) as exception:
                n2.get_related(condition + '_nodes').post(dict(id=n1.id))
            assert 'Cycle detected.' in str(exception.value)

            # Confirm nodes were not linked
            triggered_nodes = n2.get_related(condition + '_nodes').results
            assert not len(triggered_nodes), \
                'Found nodes listed, expected none. (Creates cycle in workflow):\n{0}'.format(triggered_nodes)

    @pytest.mark.parametrize('add_method', ['add_always_node', 'add_failure_node', 'add_success_node'])
    def test_cyclic_graph_with_multiple_branches(self, factories, add_method):
        """Confirms that a graph containing always and success or failure branches cannot contain cycles.

           +------------+
           | Node1      |+       Always         +------------+
           |------------|+--------------------->| Node2      |
           |            |          E1           |------------|
           |            |                       |            |
           |            |    Not allowed        |            |
           +------------+ <--xxxxxxxxxxx-+      |            |
                    +                    x      +---------+--+
                    |                    x                |
                    |                    x E5             |
                  E2|Failure             x                |
                    |or Success          +              E4|
                    |or Always        +------------+      |Always
                    v                 | Node4      |      |
               +------------+         |------------|      |
               | Node3      |         |            |      |
               |------------|         |            |<-----+
               |            |         |            |
               |            |         +------------+
               |            |
               +------------+
        """
        # Create two nodes. First node triggers second node.
        wfjt = factories.workflow_job_template()
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt)
        jt = n1.related.unified_job_template.get()  # Reuse job template from first node
        n2 = n1.add_always_node(unified_job_template=jt)
        edge2_add_method = getattr(n1, add_method)
        n3 = edge2_add_method(unified_job_template=jt) # noqa F841
        n4 = n2.add_always_node(unified_job_template=jt)

        # Attempt to create 5th edge from 4th node to 1st node should fail
        for condition in ('always', 'success', 'failure'):
            with pytest.raises(BadRequest) as exception:
                n4.get_related(condition + '_nodes').post(dict(id=n1.id))
            assert 'Cycle detected.' in str(exception.value)

            # Confirm nodes were not linked
            triggered_nodes = n4.get_related(condition + '_nodes').results
            assert len(triggered_nodes) == 0, 'node4 was related to node1, creating a cycle!'

    # Deleting workflow job templates

    def test_delete_workflow_job_template_with_single_node(self, factories):
        """When a workflow job template with a single node is deleted,
        expect node to be deleted. Job template referenced by node should
        *not* be deleted.
        """
        # Build workflow
        wfjt = factories.workflow_job_template()
        node = factories.workflow_job_template_node(workflow_job_template=wfjt)
        jt = node.related.unified_job_template.get()  # Reuse job template from first node

        # Delete WFJT
        wfjt.delete()
        with pytest.raises(NotFound, message='Expected WFJT to be deleted'):
            wfjt.get()
        with pytest.raises(NotFound, message='Expected WFJT node to be deleted'):
            node.get()
        try:
            jt.get()
        except NotFound:
            pytest.fail('Job template should still exist after deleting WFJT')

    def test_delete_workflow_job_template_with_complex_tree(self, factories):
        """When a workflow job template with a a complex tree is deleted,
        expect all nodes in tree to be deleted. Job template referenced
        by nodes should *not* be deleted.

        Workflow:
         n1
          - (always) n2
         n3
          - (success) n4
          - (failure) n5
            - (always) n6
              - (success) n7
        """
        # Build workflow
        wfjt = factories.workflow_job_template()
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt)
        jt = n1.related.unified_job_template.get()  # Reuse job template from first node
        n2 = n1.related.always_nodes.post(dict(unified_job_template=jt.id))
        n3 = factories.workflow_job_template_node(workflow_job_template=wfjt, unified_job_template=jt)
        n4 = n3.related.success_nodes.post(dict(unified_job_template=jt.id))
        n5 = n3.related.failure_nodes.post(dict(unified_job_template=jt.id))
        n6 = n5.related.always_nodes.post(dict(unified_job_template=jt.id))
        n7 = n6.related.success_nodes.post(dict(unified_job_template=jt.id))
        nodes = [n1, n2, n3, n4, n5, n6, n7]

        # Delete WFJT
        wfjt.delete()
        with pytest.raises(NotFound, message='Expected WFJT to be deleted:\n{}'.format(wfjt)):
            wfjt.get()
        for node in nodes:
            with pytest.raises(NotFound, message='Expected WFJT node to be deleted:\n{}'.format(node)):
                node.get()
        try:
            jt.get()
        except NotFound:
            pytest.fail('Job template should still exist after deleting WFJT')

    # Deleting WFJT nodes

    def test_delete_root_node(self, factories):
        """Confirm that when a noot node is deleted, the subsequent nodes become root nodes.

        Workflow:
         n1                  <----- Delete
          - (failure) n2         <--- Should become root node
            - (failure) n3
              - (always) n4
            - (success) n5
              - (always) n6
          - (success) n7        <--- Should become root node
         n8
        """
        # Build workflow
        wfjt = factories.workflow_job_template()
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt)
        jt = n1.related.unified_job_template.get()  # Reuse job template from first node
        n2 = n1.related.failure_nodes.post(dict(unified_job_template=jt.id))
        n3 = n2.related.failure_nodes.post(dict(unified_job_template=jt.id))
        n4 = n3.related.always_nodes.post(dict(unified_job_template=jt.id))
        n5 = n2.related.success_nodes.post(dict(unified_job_template=jt.id))
        n6 = n5.related.always_nodes.post(dict(unified_job_template=jt.id))
        n7 = n1.related.success_nodes.post(dict(unified_job_template=jt.id))
        n8 = factories.workflow_job_template_node(workflow_job_template=wfjt)

        # Delete node
        n1.delete()
        with pytest.raises(NotFound, message='Expected WFJT node to be deleted:\n{}'.format(n2)):
            n1.get()

        # Get tree for workflow
        tree = WorkflowTree(workflow=wfjt)

        # Build expected tree
        expected_tree = WorkflowTree()
        expected_tree.add_nodes(*[node.id for node in [n2, n3, n4, n5, n6, n7, n8]])
        expected_tree.add_edge(n2.id, n3.id, 'failure')
        expected_tree.add_edge(n3.id, n4.id, 'always')
        expected_tree.add_edge(n2.id, n5.id, 'success')
        expected_tree.add_edge(n5.id, n6.id, 'always')

        assert tree == expected_tree, 'Expected tree:\n\n{0}\n\nBut found:\n\n{1}'.format(tree, expected_tree)

    def test_delete_intermediate_node(self, factories):
        """Confirm that when an intermediate leaf node is deleted, the subsequent node becomes a root node.

        Workflow:
         n1
          - (always) n2      <----- Delete
            - (always) n3      <--- Should become root node
              - (always) n4
        """
        # Build workflow
        wfjt = factories.workflow_job_template()
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt)
        jt = n1.related.unified_job_template.get()  # Reuse job template from first node
        n2 = n1.related.always_nodes.post(dict(unified_job_template=jt.id))
        n3 = n2.related.always_nodes.post(dict(unified_job_template=jt.id))
        n4 = n3.related.always_nodes.post(dict(unified_job_template=jt.id))

        # Delete node
        n2.delete()
        with pytest.raises(NotFound, message='Expected WFJT node to be deleted:\n{}'.format(n2)):
            n2.get()

        # Get tree for workflow
        tree = WorkflowTree(workflow=wfjt)

        # Build expected tree
        expected_tree = WorkflowTree()
        expected_tree.add_nodes(n1.id, n4.id)
        expected_tree.add_node(n3.id, always_nodes=[n4.id])

        assert tree == expected_tree, 'Expected tree:\n\n{0}\n\nBut found:\n\n{1}'.format(tree, expected_tree)

    def test_delete_leaf_node(self, factories):
        """Confirm that when a leaf node is deleted, the rest of the tree is not affected

        Workflow:
         n1
          - (always) n2
        """
        # Build workflow
        wfjt = factories.workflow_job_template()
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt)
        jt = n1.related.unified_job_template.get()  # Reuse job template from first node
        n2 = n1.related.always_nodes.post(dict(unified_job_template=jt.id))

        # Delete node
        n2.delete()
        with pytest.raises(NotFound, message='Expected WFJT node to be deleted:\n{}'.format(n2)):
            n2.get()

        # Confirm intermediate node updated
        try:
            n1 = n1.get()
        except NotFound:
            pytest.fail('Intermediate node should still exist after deleting leaf node')
        n1_always_nodes = n1.get_related('always_nodes').results
        assert len(n1_always_nodes) == 0, 'Intermediate node should no longer point to leaf node:\n{0}'.format(n1_always_nodes)

    # tests for WFJT-level prompts
    # trying to use inventory that is pending deletion has some coverage in unit tests
    @pytest.mark.parametrize('source', (
        'workflow',  # test that inventory set on WFJT takes effects in spawned jobs
        'prompt',    # test that inventory provided on launch takes effect
        'rejected'   # test that if JT does not prompt for inventory, does not take effect
    ))
    def test_launch_with_workflow_inventory(self, factories, source):
        inventory = factories.inventory()
        if source == 'prompt':
            wfjt = factories.workflow_job_template(ask_inventory_on_launch=True)
        else:
            wfjt = factories.workflow_job_template(inventory=inventory)
            assert wfjt.inventory is not None

        if source == 'rejected':
            jt = factories.job_template()
        else:
            jt = factories.job_template(ask_inventory_on_launch=True)
        assert jt.inventory != wfjt.inventory

        factories.workflow_job_template_node(
            workflow_job_template=wfjt,
            unified_job_template=jt
        )

        if source == 'prompt':
            wfj = wfjt.launch(payload={'inventory': inventory.id})
        else:
            wfj = wfjt.launch()
        assert wfj.inventory == inventory.id
        node = wfj.get_related('workflow_nodes').results.pop()
        node.wait_for_job()

        job = node.get_related('job')
        if source == 'rejected':
            assert job.inventory == jt.inventory
        else:
            assert job.inventory == inventory.id

    def test_workflow_reject_inventory_on_launch(self, factories):
        """While the prompts test assert behavior about the JTs launched inside
        the workflow, this test checks that the workflow JT itself will reject
        an inventory it is not set to prompt for inventory.
        """
        inventory = factories.inventory()
        wfjt = factories.workflow_job_template()
        with pytest.raises(BadRequest) as e:
            wfjt.get_related('launch').post({'inventory': inventory.id})

        assert e.value.message == {'inventory': ['Field is not configured to prompt on launch.']}
