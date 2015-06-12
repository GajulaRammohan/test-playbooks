import pytest
from tests.api import Base_Api_Test


@pytest.mark.api
@pytest.mark.skip_selenium
class Test_Config(Base_Api_Test):
    '''
    Verify the /config endpoint displays the expected information based on the current user
    '''
    pytestmark = pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')

    def test_privileged_user(self, api_config_pg, privileged_user, user_password, current_user):
        '''Verify the project_local_paths and project_base_dir fields are present'''
        if privileged_user.username == 'admin':
            user_password = self.credentials['default']['password']

        with current_user(username=privileged_user.username, password=user_password):
            conf = api_config_pg.get()
            assert 'project_local_paths' in conf.json
            assert 'project_base_dir' in conf.json

    def test_unprivileged_user(self, api_config_pg, unprivileged_user, user_password, current_user):
        '''Verify the project_local_paths and project_base_dir fields are absent'''

        with current_user(username=unprivileged_user.username, password=user_password):
            conf = api_config_pg.get()
            assert 'project_local_paths' not in conf.json
            assert 'project_base_dir' not in conf.json
