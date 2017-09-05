from towerkit import exceptions as exc
import fauxfactory
import pytest

from tests.api import Base_Api_Test


@pytest.mark.api
@pytest.mark.skip_selenium
@pytest.mark.destructive
class TestSmartInventory(Base_Api_Test):

    pytestmark = pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')

    def test_host_update(self, factories):
        host = factories.host()
        inventory = factories.v2_inventory(organization=host.ds.inventory.ds.organization, kind='smart',
                                           host_filter="name={0}".format(host.name))
        hosts = inventory.related.hosts.get()

        host.description = fauxfactory.gen_utf8()
        assert hosts.get().results.pop().description == host.description

        host.delete()
        assert hosts.get().count == 0

    def test_host_filter_is_organization_scoped(self, factories):
        host1, host2 = [factories.v2_host(name="test_host_{0}".format(i)) for i in range(2)]
        inventory = factories.v2_inventory(organization=host1.ds.inventory.ds.organization, kind='smart',
                                           host_filter='search=test_host')

        hosts = inventory.related.hosts.get()
        assert hosts.count == 1
        assert hosts.results.pop().id == host1.id

    def test_unable_to_create_host(self, factories):
        inventory = factories.v2_inventory(host_filter='name=localhost', kind='smart')
        with pytest.raises(exc.BadRequest) as e:
            factories.v2_host(inventory=inventory)
        assert e.value[1]['inventory'] == {'detail': 'Cannot create Host for Smart Inventory'}

    def test_unable_to_create_group(self, factories):
        inventory = factories.v2_inventory(host_filter='name=localhost', kind='smart')
        with pytest.raises(exc.BadRequest) as e:
            factories.v2_group(inventory=inventory)
        assert e.value[1]['inventory'] == {'detail': 'Cannot create Group for Smart Inventory'}

    def test_unable_to_create_root_group(self, factories):
        inventory = factories.v2_inventory(host_filter='name=localhost', kind='smart')

        with pytest.raises(exc.BadRequest) as e:
            inventory.related.root_groups.post()
        assert e.value[1]['inventory'] == {'detail': 'Cannot create Group for Smart Inventory'}

    def test_unable_to_create_inventory_source(self, factories):
        inventory = factories.v2_inventory(host_filter='name=localhost', kind='smart')
        with pytest.raises(exc.BadRequest) as e:
            factories.v2_inventory_source(inventory=inventory)
        assert e.value[1]['inventory'] == {'detail': 'Cannot create Inventory Source for Smart Inventory'}

    def test_unable_to_inventory_update(self, factories):
        inventory = factories.v2_inventory(host_filter='name=localhost', kind='smart')
        with pytest.raises(exc.BadRequest) as e:
            inventory.update_inventory_sources()
        assert e.value[1] == {'detail': 'No inventory sources to update.'}

    def test_unable_to_have_insights_credential(self, factories):
        credential = factories.v2_credential(kind='insights')
        expected_error = ['Assignment not allowed for Smart Inventory']

        with pytest.raises(exc.BadRequest) as e:
            factories.v2_inventory(host_filter='name=localhost', kind='smart', insights_credential=credential.id)
        assert e.value.message['insights_credential'] == expected_error

        inventory = factories.v2_inventory(host_filter='name=localhost', kind='smart')
        with pytest.raises(exc.BadRequest) as e:
            inventory.insights_credential = credential.id
        assert e.value.message['insights_credential'] == expected_error

    def test_unable_to_update_regular_inventory_into_smart_inventory(self, factories):
        inventory = factories.v2_inventory()
        with pytest.raises(exc.MethodNotAllowed):
            inventory.patch(host_filter="name=localhost", kind="smart")

    def test_able_to_update_smart_inventory_into_regular_inventory(self, factories):
        host = factories.v2_host()
        inventory = factories.v2_inventory(organization=host.ds.inventory.ds.organization,
                                           host_filter="name={0}".format(host.name), kind="smart")
        assert inventory.related.hosts.get().count == 1

        inventory.patch(host_filter="", kind="")
        assert inventory.related.hosts.get().count == 0

    def test_launch_ahc_with_smart_inventory(self, factories):
        inventory = factories.v2_inventory()
        parent_group, child_group = [factories.v2_group(inventory=inventory) for _ in range(2)]
        parent_group.add_group(child_group)
        for group in (parent_group, child_group):
            host = factories.v2_host(name="test_host_{0}".format(group.name), inventory=inventory)
            group.add_host(host)
        factories.v2_host(name="test_host_root", inventory=inventory)

        smart_inventory = factories.v2_inventory(organization=inventory.ds.organization, host_filter="search=test_host",
                                                 kind="smart")
        hosts = smart_inventory.related.hosts.get().results
        assert len(hosts) == 3

        ahc = factories.v2_ad_hoc_command(inventory=smart_inventory).wait_until_completed()
        assert ahc.is_successful
        assert ahc.summary_fields.inventory.id == smart_inventory.id
        assert ahc.inventory == smart_inventory.id

        assert ahc.related.inventory.get().id == smart_inventory.id
        assert ahc.related.events.get().count > 0
        activity_stream = ahc.related.activity_stream.get()
        assert activity_stream.count == 1
        assert activity_stream.results.pop().operation == 'create'

    def test_launch_job_template_with_smart_inventory(self, factories):
        inventory = factories.v2_inventory()
        parent_group, child_group = [factories.v2_group(inventory=inventory) for _ in range(2)]
        parent_group.add_group(child_group)
        for group in (parent_group, child_group):
            host = factories.v2_host(name="test_host_{0}".format(group.name), inventory=inventory)
            group.add_host(host)
        factories.v2_host(name="test_host_root", inventory=inventory)

        smart_inventory = factories.v2_inventory(organization=inventory.ds.organization, host_filter="search=test_host",
                                                 kind="smart")
        hosts = smart_inventory.related.hosts.get().results
        assert len(hosts) == 3

        jt = factories.v2_job_template(inventory=smart_inventory)
        job = jt.launch().wait_until_completed()
        assert job.is_successful
        assert job.summary_fields.inventory.id == smart_inventory.id
        assert job.inventory == smart_inventory.id

        assert job.related.inventory.get().id == smart_inventory.id
        assert job.related.job_host_summaries.get().count == 3
        assert job.related.job_events.get().count > 0
        activity_stream = job.related.activity_stream.get()
        assert activity_stream.count == 1
        assert activity_stream.results.pop().operation == 'create'

    def test_host_update_after_ahc(self, factories):
        host = factories.v2_host()
        smart_inventory = factories.v2_inventory(organization=host.ds.inventory.ds.organization, kind="smart",
                                                 host_filter="name={0}".format(host.name))
        ahc = factories.v2_ad_hoc_command(inventory=smart_inventory).wait_until_completed()

        ahcs = host.related.ad_hoc_commands.get()
        assert ahcs.count == 1
        assert ahcs.results.pop().id == ahc.id
        assert host.get().related.ad_hoc_command_events.get().count > 0

    def test_host_update_after_job(self, factories):
        host = factories.v2_host()
        smart_inventory = factories.v2_inventory(organization=host.ds.inventory.ds.organization, kind="smart",
                                                 host_filter="name={0}".format(host.name))
        job = factories.v2_job_template(inventory=smart_inventory).launch().wait_until_completed()

        assert job.is_successful
        job_host_summaries = job.related.job_host_summaries.get()
        assert job_host_summaries.count == 1
        jhs = job_host_summaries.results.pop()

        assert host.get().summary_fields.last_job.id == job.id
        assert host.summary_fields.last_job_host_summary.id == jhs.id
        recent_jobs = host.summary_fields.recent_jobs
        assert len(recent_jobs) == 1
        assert recent_jobs.pop().id == job.id

        assert host.last_job == job.id
        assert host.last_job_host_summary == jhs.id

        assert host.get().related.job_host_summaries.get().results.pop().id == jhs.id
        assert host.related.job_events.get().count > 0
        assert host.related.last_job.get().id == job.id
        assert host.related.last_job_host_summary.get().id == jhs.id

    def test_host_sources_original_inventory(self, factories):
        host = factories.v2_host()
        smart_inventory = factories.v2_inventory(organization=host.ds.inventory.ds.organization, kind="smart",
                                                 host_filter="name={0}".format(host.name))

        assert host.related.inventory.get().id == host.ds.inventory.id
        assert host.summary_fields.inventory.id == host.ds.inventory.id
        assert host.inventory == host.ds.inventory.id

    def test_duplicate_hosts(self, factories):
        org = factories.v2_organization()
        inv1, inv2 = [factories.v2_inventory(organization=org) for _ in range(2)]
        inventory = factories.v2_inventory(organization=org, host_filter="name=test_host", kind="smart")

        hosts = []
        for inv in (inv1, inv2):
            host = factories.v2_host(name='test_host', inventory=inv)
            hosts.append(host)

        inv_hosts = inventory.related.hosts.get()
        assert inv_hosts.count == 1
        assert inv_hosts.results.pop().id == min([host.id for host in hosts])

    def test_smart_inventory_deletion_should_not_cascade_delete_hosts(self, factories):
        host = factories.v2_host()
        inventory = factories.v2_inventory(organization=host.ds.inventory.ds.organization, kind='smart',
                                           host_filter='name={0}'.format(host.name))
        assert inventory.related.hosts.get().count == 1

        inventory.delete().wait_until_deleted()
        host.get()
