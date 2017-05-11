import pytest

from tests.api import Base_Api_Test


def find_settings(setting_pg, substrings):
    """Find settings given a list of matching substrings."""
    keys = []
    for key in setting_pg.json:
        if any(substring in key for substring in substrings):
            keys.append(key)
    return keys


@pytest.mark.api
@pytest.mark.destructive
@pytest.mark.skip_selenium
class Test_Auth(Base_Api_Test):

    pytestmark = pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')

    def test_default_entries(self, v1):
        """By default /api/v1/auth/ should not contain any entries."""
        auth = v1.walk('/api/v1/auth/')
        assert auth.json == {}, \
            "Unexpected value for /api/v1/auth/."

    def test_updated_entries(self, v1, sso_settings_pg, configure_auth):
        """Update sso settings page and verify that /api/v1/auth/ updates accordingly."""
        configure_auth(sso_settings_pg)

        # assert expected entry found
        auth = v1.walk('/api/v1/auth/')
        assert len(auth.json) == 1, \
            "Expected to have one result under /api/v1/auth/."
        endpoint_name = sso_settings_pg.endpoint.replace('/api/v1/settings/', '').strip('/')
        assert endpoint_name in auth.json, \
            "Unexpected result found with /api/v1/auth/. Expected '{0}.'".format(endpoint_name)
        # assert entry contains expected contents
        assert auth.json[endpoint_name]["login_url"] == "/sso/login/" + endpoint_name + "/", \
            "Unexpected value for login_url."
        callback_setting = find_settings(sso_settings_pg, ['CALLBACK']).pop()
        assert auth.json[endpoint_name]["complete_url"] == sso_settings_pg.json[callback_setting]

    def test_reset_entries(self, v1):
        """Our /api/v1/auth/ endpoint should not contain any entries after settings reset."""
        auth = v1.walk('/api/v1/auth/')
        assert auth.json == {}, \
            "Unexpected value for /api/v1/auth/."
