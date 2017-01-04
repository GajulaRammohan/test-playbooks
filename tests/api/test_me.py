import pytest
from tests.api import Base_Api_Test


@pytest.mark.api
@pytest.mark.destructive
@pytest.mark.skip_selenium
class Test_Me(Base_Api_Test):
    """
    Verify the /me endpoint displays the expected information based on the current user
    """

    def test_get(self, api_me_pg, all_users, user_password):
        """
        Verify that the /api/v1/me endpoint returns the expected information
        when authenticated as various user types.
        """
        for user in all_users:
            with self.current_user(user.username, user_password):
                me_pg = api_me_pg.get()

                # assert number of items
                assert me_pg.count == 1, "Unexpected number of results from /api/v1/me"

                me_user = me_pg.results.pop()
                for attr in ('username', 'first_name', 'last_name', 'is_superuser'):
                    assert getattr(me_user, attr) == getattr(user, attr), "The " \
                        "%s attribute does not match from the /api/v1/me endpoint " \
                        "(%s != %s)" % (attr, getattr(me_user, attr), getattr(user, attr))
