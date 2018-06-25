import pytest

from tests.api import Base_Api_Test


@pytest.mark.api
@pytest.mark.requires_traditional_cluster
@pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')
class TestIsolatedFactCache(Base_Api_Test):

    @pytest.fixture
    def isolated_instance_group(self, v2):
        return v2.instance_groups.get(name='protected').results.pop()

    def assert_updated_facts(self, ansible_facts):
        assert ansible_facts.module_setup
        assert ansible_facts.ansible_distribution == 'RedHat'
        assert ansible_facts.ansible_machine == 'x86_64'
        assert ansible_facts.ansible_system == 'Linux'

    def test_ingest_facts_with_gather_facts_on_isolated_node(self, factories, isolated_instance_group):
        host = factories.v2_host()
        ansible_facts = host.related.ansible_facts.get()
        assert ansible_facts.json == {}

        jt = factories.v2_job_template(inventory=host.ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        jt.add_instance_group(isolated_instance_group)
        assert jt.launch().wait_until_completed().is_successful

        ansible_facts = host.related.ansible_facts.get()
        self.assert_updated_facts(ansible_facts)

    def test_consume_facts_with_multiple_hosts_on_isolated_node(self, factories, isolated_instance_group):
        inventory = factories.v2_inventory()
        hosts = [factories.v2_host(inventory=inventory) for _ in range(3)]

        jt = factories.v2_job_template(inventory=hosts[0].ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        jt.add_instance_group(isolated_instance_group)
        assert jt.launch().wait_until_completed().is_successful

        jt.patch(playbook='use_facts.yml', job_tags='ansible_facts')
        job = jt.launch().wait_until_completed()
        assert job.is_successful

        ansible_facts = hosts.pop().related.ansible_facts.get()  # facts should be the same between hosts
        assert job.result_stdout.count(ansible_facts.ansible_distribution) == 3
        assert job.result_stdout.count(ansible_facts.ansible_machine) == 3
        assert job.result_stdout.count(ansible_facts.ansible_system) == 3

    def test_clear_facts_on_isolated_node(self, factories, isolated_instance_group):
        host = factories.v2_host()

        jt = factories.v2_job_template(inventory=host.ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        jt.add_instance_group(isolated_instance_group)
        assert jt.launch().wait_until_completed().is_successful
        ansible_facts = host.related.ansible_facts.get()
        self.assert_updated_facts(ansible_facts)

        jt.playbook = 'clear_facts.yml'
        assert jt.launch().wait_until_completed().is_successful
        assert ansible_facts.get().json == {}
