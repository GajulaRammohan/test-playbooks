# -*- coding: utf-8 -*-
import json

from towerkit.utils import to_str
import fauxfactory
import pytest

from tests.api import Base_Api_Test


@pytest.mark.api
@pytest.mark.skip_selenium
@pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')
class TestFactCache(Base_Api_Test):

    def assert_updated_facts(self, ansible_facts):
        """Perform basic validation on host details ansible_facts."""
        assert ansible_facts.module_setup
        assert 'ansible_distribution' in ansible_facts
        assert 'ansible_machine' in ansible_facts
        assert 'ansible_system' in ansible_facts

    def test_ingest_facts_with_gather_facts_playbook(self, factories):
        host = factories.v2_host()
        ansible_facts = host.related.ansible_facts.get()
        assert not ansible_facts.json

        jt = factories.v2_job_template(inventory=host.ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        assert jt.launch().wait_until_completed().is_successful

        self.assert_updated_facts(ansible_facts.get())

    @pytest.fixture
    def scan_facts_job_template(self, factories):
        host = factories.v2_host()
        inventory = host.ds.inventory
        organization = inventory.ds.organization
        scm_cred, ssh_cred = [factories.v2_credential(kind=k, organization=organization) for k in ('scm', 'ssh')]
        project = factories.v2_project(scm_url='git@github.com:ansible/tower-fact-modules.git', credential=scm_cred)
        return factories.v2_job_template(description="3.2 scan_facts JT %s" % fauxfactory.gen_utf8(),
                                         project=project, credential=ssh_cred, inventory=inventory,
                                         playbook='scan_facts.yml', use_fact_cache=True)

    @pytest.mark.requires_single_instance
    def test_ingest_facts_with_tower_scan_playbook(self, request, factories, ansible_runner, is_docker,
                                                   scan_facts_job_template):
        machine_id = "4da7d1f8-14f3-4cdc-acd5-a3465a41f25d"
        ansible_runner.file(path='/etc/redhat-access-insights', state="directory")
        ansible_runner.shell('echo -n {0} > /etc/redhat-access-insights/machine-id'.format(machine_id))
        request.addfinalizer(lambda: ansible_runner.file(path='/etc/redhat-access-insights', state="absent"))

        assert scan_facts_job_template.launch().wait_until_completed().is_successful

        ansible_facts = scan_facts_job_template.ds.inventory.related.hosts.get().results[0].related.ansible_facts.get()
        self.assert_updated_facts(ansible_facts)

        assert ansible_facts.services['network'] if is_docker else ansible_facts.services['sshd.service']
        assert ansible_facts.packages['which'] if is_docker else ansible_facts.packages['ansible-tower']
        assert ansible_facts.insights['system_id'] == machine_id

    def test_ingest_facts_with_host_with_unicode_hostname(self, factories):
        host = factories.v2_host(name=fauxfactory.gen_utf8())
        jt = factories.v2_job_template(inventory=host.ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        assert jt.launch().wait_until_completed().is_successful

        ansible_facts = host.related.ansible_facts.get()
        self.assert_updated_facts(ansible_facts)

    def test_ingest_facts_with_host_with_hostname_with_spaces(self, factories):
        host = factories.v2_host(name="hostname with spaces")
        jt = factories.v2_job_template(inventory=host.ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        assert jt.launch().wait_until_completed().is_successful

        ansible_facts = host.related.ansible_facts.get()
        self.assert_updated_facts(ansible_facts)

    def test_consume_facts_with_single_host(self, factories):
        host = factories.v2_host()
        jt = factories.v2_job_template(inventory=host.ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        assert jt.launch().wait_until_completed().is_successful

        jt.patch(playbook='use_facts.yml', job_tags='ansible_facts')
        job = jt.launch().wait_until_completed()
        assert job.is_successful

        ansible_facts = host.related.ansible_facts.get()
        assert ansible_facts.ansible_distribution in job.result_stdout
        assert ansible_facts.ansible_machine in job.result_stdout
        assert ansible_facts.ansible_system in job.result_stdout

    def test_consume_facts_with_multiple_hosts(self, factories):
        inventory = factories.v2_inventory()
        hosts = [factories.v2_host(inventory=inventory) for _ in range(3)]

        jt = factories.v2_job_template(inventory=hosts[0].ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        assert jt.launch().wait_until_completed().is_successful

        jt.patch(playbook='use_facts.yml', job_tags='ansible_facts')
        job = jt.launch().wait_until_completed()
        assert job.is_successful

        ansible_facts = hosts.pop().related.ansible_facts.get()  # facts should be the same between hosts
        assert job.result_stdout.count(ansible_facts.ansible_distribution) == 3
        assert job.result_stdout.count(ansible_facts.ansible_machine) == 3
        assert job.result_stdout.count(ansible_facts.ansible_system) == 3

        for host in hosts:
            assert host.get().summary_fields.last_job.id == job.id

    def test_consume_facts_with_multiple_hosts_and_limit(self, factories):
        inventory = factories.v2_inventory()
        hosts = [factories.v2_host(inventory=inventory) for _ in range(3)]
        target_host = hosts.pop()

        jt = factories.v2_job_template(inventory=target_host.ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        scan_job = jt.launch().wait_until_completed()
        assert scan_job.is_successful

        jt.patch(playbook='use_facts.yml', job_tags='ansible_facts')
        jt.limit = target_host.name
        fact_job = jt.launch().wait_until_completed()
        assert fact_job.is_successful

        ansible_facts = target_host.related.ansible_facts.get()
        assert fact_job.result_stdout.count(ansible_facts.ansible_distribution) == 1
        assert fact_job.result_stdout.count(ansible_facts.ansible_machine) == 1
        assert fact_job.result_stdout.count(ansible_facts.ansible_system) == 1

        assert target_host.get().summary_fields.last_job.id == fact_job.id
        for host in hosts:
            assert host.get().summary_fields.last_job.id == scan_job.id

    def test_consume_updated_facts(self, factories):
        host = factories.v2_host()

        jt = factories.v2_job_template(inventory=host.ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        assert jt.launch().wait_until_completed().is_successful
        ansible_facts = host.related.ansible_facts.get()
        first_time = ansible_facts.ansible_date_time.time

        assert jt.launch().wait_until_completed().is_successful
        second_time = ansible_facts.get().ansible_date_time.time
        assert second_time > first_time

        jt.patch(playbook='use_facts.yml', job_tags='ansible_facts')
        job = jt.launch().wait_until_completed()
        assert job.is_successful

        self.assert_updated_facts(ansible_facts)
        assert second_time in job.result_stdout

    def test_consume_facts_with_custom_ansible_module(self, factories):
        host = factories.v2_host()
        jt = factories.v2_job_template(inventory=host.ds.inventory, playbook='scan_custom.yml', use_fact_cache=True)
        job = jt.launch().wait_until_completed()
        assert job.is_successful

        target_job_events = job.related.job_events.get(event="runner_on_ok", task="test_scan_facts")
        assert target_job_events.count == 1
        target_job_event = target_job_events.results.pop()
        ansible_facts = target_job_event.event_data.res.ansible_facts

        # verify ingested facts
        assert ansible_facts.string == "abc"
        assert to_str(ansible_facts.unicode_string) == "鵟犭酜귃ꔀꈛ竳䙭韽ࠔ"
        assert ansible_facts.int == 1
        assert ansible_facts.float == 1.0
        assert ansible_facts.bool is True
        assert ansible_facts.null is None
        assert ansible_facts.list == ["abc", 1, 1.0, True, None, [], {}]
        assert ansible_facts.obj == dict(string="abc", int=1, float=1.0, bool=True, null=None, list=[], obj={})
        assert ansible_facts.empty_list == []
        assert ansible_facts.empty_obj == {}

        jt.patch(playbook='use_facts.yml', job_tags='custom_facts')
        job = jt.launch().wait_until_completed()
        assert job.is_successful

        # verify facts consumption
        assert '"msg": "abc"' in job.json.result_stdout
        assert '"msg": "鵟犭酜귃ꔀꈛ竳䙭韽ࠔ"' in to_str(job.json.result_stdout)
        assert '"msg": 1' in job.json.result_stdout
        assert '"msg": 1.0' in job.json.result_stdout
        assert '"msg": true' in job.json.result_stdout
        assert '"msg": null' in job.json.result_stdout
        assert '"msg": [\r\n' in job.json.result_stdout
        assert '"msg": {\r\n' in job.json.result_stdout
        assert '"msg": []' in job.json.result_stdout
        assert '"msg": {}' in job.json.result_stdout

    def test_clear_facts(self, factories, ansible_version_cmp):
        if ansible_version_cmp("2.3") < 0:
            pytest.skip("Not supported on Ansible-2.2.")
        host = factories.v2_host()
        jt = factories.v2_job_template(inventory=host.ds.inventory, playbook='gather_facts.yml', use_fact_cache=True)
        assert jt.launch().wait_until_completed().is_successful

        jt.playbook = 'clear_facts.yml'
        assert jt.launch().wait_until_completed().is_successful

        jt.patch(playbook='use_facts.yml', job_tags='ansible_facts')
        job = jt.launch().wait_until_completed()
        assert job.status == 'failed'
        assert "The error was: 'ansible_distribution' is undefined" in job.result_stdout

    @pytest.mark.ansible_integration
    def test_scan_file_paths_are_sourced(self, scan_facts_job_template):
        scan_file_paths = ('/tmp', '/bin')
        scan_facts_job_template.extra_vars = json.dumps(dict(scan_file_paths=','.join(scan_file_paths)))

        job = scan_facts_job_template.launch().wait_until_completed()
        assert job.is_successful

        host = scan_facts_job_template.related.inventory.get().related.hosts.get().results[0]
        files = host.related.ansible_facts.get().files

        for file_path in [f.path for f in files]:
            assert any([file_path.startswith(path) for path in scan_file_paths])

    @pytest.mark.requires_isolation
    @pytest.mark.ansible_integration
    def test_scan_file_paths_are_traversed(self, v2, request, ansible_runner, scan_facts_job_template):
        jobs_settings = v2.settings.get().get_endpoint('jobs')
        prev_proot_show_paths = jobs_settings.AWX_PROOT_SHOW_PATHS
        jobs_settings.AWX_PROOT_SHOW_PATHS = prev_proot_show_paths + ["/tmp/test"]
        request.addfinalizer(lambda: jobs_settings.patch(AWX_PROOT_SHOW_PATHS=prev_proot_show_paths))

        dir_path = '/tmp/test/directory/traversal/is/working'
        res = ansible_runner.file(path=dir_path, state='directory').values()[0]
        assert not res.get('failed') and res.get('changed')

        test_dir = '/tmp/test'
        request.addfinalizer(lambda: ansible_runner.file(path=test_dir, state='absent'))

        file_path = dir_path + '/some_file'
        res = ansible_runner.file(path=file_path, state='touch').values()[0]
        assert not res.get('failed') and res.get('changed')

        extra_vars = dict(scan_file_paths=test_dir, scan_use_recursive=True)
        scan_facts_job_template.patch(extra_vars=json.dumps(extra_vars))

        job = scan_facts_job_template.launch().wait_until_completed()
        assert job.is_successful

        host = scan_facts_job_template.related.inventory.get().related.hosts.get().results[0]
        files = host.related.ansible_facts.get().files
        assert len(files) == 1
        assert files[0].path == file_path

    @pytest.mark.ansible_integration
    def test_file_scan_job_provides_checksums(self, scan_facts_job_template):
        scan_facts_job_template.extra_vars = json.dumps(dict(scan_file_paths='/tmp,/bin', scan_use_checksum=True))

        job = scan_facts_job_template.launch().wait_until_completed()
        assert job.is_successful

        host = scan_facts_job_template.related.inventory.get().related.hosts.get().results[0]
        files = host.related.ansible_facts.get().files

        for file in files:
            if not file.isdir and file.roth:
                assert file.checksum
