import pytest
import logging

from towerkit.exceptions import BadRequest, NotFound

from tests.api import Base_Api_Test
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
@pytest.mark.skip_selenium
@pytest.mark.destructive
class Test_Workflow_Job_Templates(Base_Api_Test):

    pytestmark = pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')

    # Graph Topology Validation
    # Graphs should not (1) converge (2) contain cycles or
    # (3) trigger the same node in both always_nodes and {success,failure}_nodes

    def test_converging_nodes(self, factories):
        '''Confirms that two nodes cannot trigger the same node'''
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

    def test_single_node_references_itself(self, factories):
        '''Confirms that a node cannot trigger itself'''
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
        '''Confirms that a graph cannot contain a cycle'''
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

    # TODO: Add more advaced test for cyclic graphs (e.g. testing graph with depth, braches, usage
    #      of different types of edges)

    def test_node_triggers_should_be_mutually_exclusive(self, factories):
        '''Confirms that if a node is listed under `always_nodes`, it cannot also be
           listed under `{success, failure}_nodes`.'''
        # Create two nodes. First node set to _always_ trigger second node.
        wfjt = factories.workflow_job_template()
        n1 = factories.workflow_job_template_node(workflow_job_template=wfjt)
        jt = n1.related.unified_job_template.get()  # Reuse job template from first node
        n2 = n1.related.always_nodes.post(dict(unified_job_template=jt.id))

        # First node set to trigger second node using success / failure
        for condition in ('success', 'failure'):
            with pytest.raises(BadRequest) as exception:
                n1.get_related(condition + '_nodes').post(dict(id=n2.id))
            error_msg = 'Cannot associate {}_nodes when always_nodes have been associated.'.format(condition)
            assert error_msg in str(exception.value)

            # Confirm nodes were not linked
            triggered_nodes = n1.get_related(condition + '_nodes').results
            assert not len(triggered_nodes), \
                'Found nodes listed, expected none. (Creates triggers that should be mutually exclusive):\n{0}'.format(triggered_nodes)

    # Deleting workflow job templates

    def test_delete_workflow_job_template_with_single_node(self, factories):
        '''When a workflow job template with a single node is deleted,
           expect node to be deleted. Job template referenced by node should
           *not* be deleted.'''
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
        '''When a workflow job template with a a complex tree is deleted,
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
           '''
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
        '''Confirm that when a noot node is deleted, the subsequent nodes become root nodes.

           Workflow:
            n1                  <----- Delete
             - (failure) n2         <--- Should become root node
               - (failure) n3
                 - (always) n4
               - (success) n5
                 - (always) n6
             - (success) n7        <--- Should become root node
            n8
        '''
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
        '''Confirm that when an intermediate leaf node is deleted, the subsequent node becomes a root node.

           Workflow:
            n1
             - (always) n2      <----- Delete
               - (always) n3      <--- Should become root node
                 - (always) n4
        '''
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
        '''Confirm that when a leaf node is deleted, the rest of the tree is not affected

           Workflow:
            n1
             - (always) n2
           '''
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
