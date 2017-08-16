import pytest
import httplib

import towerkit.exceptions as exc

from tests.lib.helpers.rbac_utils import assert_response_raised, check_read_access
from tests.api import Base_Api_Test


@pytest.mark.api
@pytest.mark.rbac
@pytest.mark.skip_selenium
@pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')
class TestSmartInventoryRBAC(Base_Api_Test):

    def test_unprivileged_user(self, factories):
        host = factories.v2_host()
        inventory = factories.v2_inventory(kind='smart', host_filter='name={0}'.format(host.name))
        user = factories.user()

        with self.current_user(username=user.username, password=user.password):
            check_read_access(inventory, unprivileged=True)

            with pytest.raises(exc.Forbidden):
                inventory.related.ad_hoc_commands.post()

            assert_response_raised(host, httplib.FORBIDDEN)
            assert_response_raised(inventory, httplib.FORBIDDEN)

    @pytest.mark.github('https://github.com/ansible/ansible-tower/issues/7382')
    @pytest.mark.parametrize("agent", ["user", "team"])
    def test_admin_role(self, set_test_roles, agent, factories):
        host = factories.v2_host()
        inventory = factories.v2_inventory(kind='smart', host_filter='name={0}'.format(host.name))
        user = factories.user()

        set_test_roles(user, inventory, agent, "admin")

        with self.current_user(username=user.username, password=user.password):
            check_read_access(inventory, ["organization"])
            assert_response_raised(host, httplib.FORBIDDEN)
            assert_response_raised(inventory, httplib.OK)

    @pytest.mark.parametrize("agent", ["user", "team"])
    def test_use_role(self, set_test_roles, agent, factories):
        host = factories.v2_host()
        inventory = factories.v2_inventory(kind='smart', host_filter='name={0}'.format(host.name))
        user = factories.user()

        set_test_roles(user, inventory, agent, "use")

        with self.current_user(username=user.username, password=user.password):
            check_read_access(inventory, ["organization"])
            assert_response_raised(host, httplib.FORBIDDEN)
            assert_response_raised(inventory, httplib.FORBIDDEN)

    @pytest.mark.parametrize("agent", ["user", "team"])
    def test_adhoc_role(self, set_test_roles, agent, factories):
        host = factories.v2_host()
        inventory = factories.v2_inventory(kind='smart', host_filter='name=localhost')
        user = factories.user()

        set_test_roles(user, inventory, agent, "ad hoc")

        with self.current_user(username=user.username, password=user.password):
            check_read_access(inventory, ["organization"])
            assert_response_raised(host, httplib.FORBIDDEN)
            assert_response_raised(inventory, httplib.FORBIDDEN)

    @pytest.mark.parametrize("agent", ["user", "team"])
    def test_read_role(self, set_test_roles, agent, factories):
        host = factories.v2_host()
        inventory = factories.v2_inventory(kind='smart', host_filter='name={0}'.format(host.name))
        user = factories.user()

        set_test_roles(user, inventory, agent, "read")

        with self.current_user(username=user.username, password=user.password):
            check_read_access(inventory, ["organization"])
            assert_response_raised(host, httplib.FORBIDDEN)
            assert_response_raised(inventory, httplib.FORBIDDEN)

    @pytest.mark.parametrize('role', ['admin', 'use', 'ad hoc', 'read'])
    def test_launch_command_with_smart_inventory(self, factories, role):
        ALLOWED_ROLES = ['admin', 'ad hoc']
        REJECTED_ROLES = ['use', 'read']

        host = factories.v2_host()
        inventory = factories.v2_inventory(kind='smart', host_filter='name={0}'.format(host.name))
        user = factories.user()
        credential = factories.v2_credential(user=user)

        inventory.set_object_roles(user, role)

        with self.current_user(username=user.username, password=user.password):
            if role in ALLOWED_ROLES:
                ahc = factories.v2_ad_hoc_command(inventory=inventory,
                                                  credential=credential,
                                                  module_name="ping").wait_until_completed()
                assert ahc.is_successful
            elif role in REJECTED_ROLES:
                with pytest.raises(exc.Forbidden):
                    factories.v2_ad_hoc_command(inventory=inventory,
                                                credential=credential,
                                                module_name="ping")
            else:
                raise ValueError("Received unhandled inventory role.")
