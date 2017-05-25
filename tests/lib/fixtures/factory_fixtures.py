from towerkit.utils import PseudoNamespace
from towerkit.api import mixins, pages
import pytest


class HasCreateFactory(object):

    model = None

    @classmethod
    def __call__(cls, request, *args, **kwargs):
        connection = request.getfixturevalue('testsetup').api

        provided_has_creates = mixins.has_create.all_instantiated_dependencies(*kwargs.items())

        has_create = cls.model(connection).create(**kwargs)

        for resource in mixins.has_create.all_instantiated_dependencies(has_create):
            if resource not in provided_has_creates:
                request.addfinalizer(resource.silent_cleanup)

        return has_create

    to_teardown = set()

    @classmethod
    def payload(cls, request, **kwargs):
        connection = request.getfixturevalue('testsetup').api

        provided_has_creates = mixins.has_create.all_instantiated_dependencies(*kwargs.items())

        payload = cls.model(connection).create_payload(**kwargs)

        def register_teardown(teardown):
            request.addfinalizer(teardown.silent_cleanup)
            cls.to_teardown.remove(teardown)

        resources = []
        for resource_type in payload.ds:
            try:
                resource = payload.ds[resource_type]
                resources.append(resource)
            except AttributeError:
                pass

        for resource in mixins.has_create.all_instantiated_dependencies(*resources):
            if resource not in provided_has_creates and resource not in cls.to_teardown:
                cls.to_teardown.add(resource)
                register_teardown(resource)

        return payload


class OrganizationFactory(HasCreateFactory):
    model = pages.Organization


class V2OrganizationFactory(HasCreateFactory):
    model = pages.V2Organization


class UserFactory(HasCreateFactory):
    model = pages.User


class V2UserFactory(HasCreateFactory):
    model = pages.V2User


class WorkflowJobTemplateFactory(HasCreateFactory):
    model = pages.WorkflowJobTemplate


class V2WorkflowJobTemplateFactory(HasCreateFactory):
    model = pages.V2WorkflowJobTemplate


class CredentialFactory(HasCreateFactory):
    model = pages.Credential


class V2CredentialFactory(HasCreateFactory):
    model = pages.V2Credential


class CredentialTypeFactory(HasCreateFactory):
    model = pages.CredentialType


class InventoryFactory(HasCreateFactory):
    model = pages.Inventory


class V2InventoryFactory(HasCreateFactory):
    model = pages.V2Inventory


class InventoryScriptFactory(HasCreateFactory):
    model = pages.InventoryScript


class V2InventoryScriptFactory(HasCreateFactory):
    model = pages.V2InventoryScript


class LabelFactory(HasCreateFactory):
    model = pages.Label


class V2LabelFactory(HasCreateFactory):
    model = pages.V2Label


class NotificationTemplateFactory(HasCreateFactory):
    model = pages.NotificationTemplate


class V2NotificationTemplateFactory(HasCreateFactory):
    model = pages.V2NotificationTemplate


class ProjectFactory(HasCreateFactory):
    model = pages.Project


class V2ProjectFactory(HasCreateFactory):
    model = pages.V2Project


class TeamFactory(HasCreateFactory):
    model = pages.Team


class V2TeamFactory(HasCreateFactory):
    model = pages.V2Team


class AdHocCommandFactory(HasCreateFactory):
    model = pages.AdHocCommand


class V2AdHocCommandFactory(HasCreateFactory):
    model = pages.V2AdHocCommand


class GroupFactory(HasCreateFactory):
    model = pages.Group


class V2GroupFactory(HasCreateFactory):
    model = pages.V2Group


class HostFactory(HasCreateFactory):
    model = pages.Host


class V2HostFactory(HasCreateFactory):
    model = pages.V2Host


class JobTemplateFactory(HasCreateFactory):
    model = pages.JobTemplate


class V2JobTemplateFactory(HasCreateFactory):
    model = pages.V2JobTemplate


class WorkflowJobTemplateNodeFactory(HasCreateFactory):
    model = pages.WorkflowJobTemplateNode


class V2WorkflowJobTemplateNodeFactory(HasCreateFactory):
    model = pages.V2WorkflowJobTemplateNode


class FactoryFixture(object):
    """This class is used within the factory fixture definitions below to wrap
    up the request fixture with a factory class so we don't need to explicitly
    bring the request fixture into every test that needs to use a factory.
    """

    def __init__(self, request, has_create_factory):
        self.request = request
        self._has_create_factory = has_create_factory()

    def __call__(self, **kwargs):
        return self._has_create_factory(request=self.request, **kwargs)

    def payload(self, **kwargs):
        return self._has_create_factory.payload(self.request, **kwargs)


def factory_namespace(request):
    return PseudoNamespace(
        ad_hoc_command=FactoryFixture(request, AdHocCommandFactory),
        credential=FactoryFixture(request, CredentialFactory),
        credential_type=FactoryFixture(request, CredentialTypeFactory),
        group=FactoryFixture(request, GroupFactory),
        host=FactoryFixture(request, HostFactory),
        inventory=FactoryFixture(request, InventoryFactory),
        inventory_script=FactoryFixture(request, InventoryScriptFactory),
        job_template=FactoryFixture(request, JobTemplateFactory),
        label=FactoryFixture(request, LabelFactory),
        notification_template=FactoryFixture(request, NotificationTemplateFactory),
        organization=FactoryFixture(request, OrganizationFactory),
        project=FactoryFixture(request, ProjectFactory),
        team=FactoryFixture(request, TeamFactory),
        user=FactoryFixture(request, UserFactory),
        workflow_job_template=FactoryFixture(request, WorkflowJobTemplateFactory),
        workflow_job_template_node=FactoryFixture(request, WorkflowJobTemplateNodeFactory),
        v2_ad_hoc_command=FactoryFixture(request, V2AdHocCommandFactory),
        v2_credential=FactoryFixture(request, V2CredentialFactory),
        v2_group=FactoryFixture(request, V2GroupFactory),
        v2_host=FactoryFixture(request, V2HostFactory),
        v2_inventory=FactoryFixture(request, V2InventoryFactory),
        v2_inventory_script=FactoryFixture(request, V2InventoryScriptFactory),
        v2_job_template=FactoryFixture(request, V2JobTemplateFactory),
        v2_label=FactoryFixture(request, V2LabelFactory),
        v2_notification_template=FactoryFixture(request, V2NotificationTemplateFactory),
        v2_organization=FactoryFixture(request, V2OrganizationFactory),
        v2_project=FactoryFixture(request, V2ProjectFactory),
        v2_team=FactoryFixture(request, V2TeamFactory),
        v2_user=FactoryFixture(request, V2UserFactory),
        v2_workflow_job_template=FactoryFixture(request, V2WorkflowJobTemplateFactory),
        v2_workflow_job_template_node=FactoryFixture(request, V2WorkflowJobTemplateNodeFactory)
    )


@pytest.fixture
def factories(request):
    """Inject a function-scoped factory namespace into your test context"""
    return factory_namespace(request)
