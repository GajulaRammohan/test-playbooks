import logging
import json

import towerkit.exceptions as exc
from towerkit import utils
import fauxfactory
import pytest

from tests.api import Base_Api_Test


log = logging.getLogger(__name__)


@pytest.mark.api
@pytest.mark.skip_selenium
@pytest.mark.destructive
class TestJobTemplateSurveys(Base_Api_Test):

    pytestmark = pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')

    @pytest.mark.ha_tower
    @pytest.mark.parametrize("launch_time_vars",
                             ["{'non_survey_variable': false, 'submitter_email': 'sample_email@maffenmox.edu'}",
                              "---\nnon_survey_variable: false\nsubmitter_email: sample_email@maffenmox.edu"],
                              ids=['json', 'yaml'])
    def test_launch_with_survey_and_excluded_variables_in_payload(self, job_template,
                                                                  optional_survey_spec_without_defaults,
                                                                  launch_time_vars):
        """Tests that when ask_variables_at_launch is disabled that only survey variables are
        received and make it to our job. Here, "submitter_email" is our only survey variable.
        """
        job_template.add_survey(spec=optional_survey_spec_without_defaults)
        assert not job_template.ask_variables_on_launch

        job = job_template.launch(dict(extra_vars=launch_time_vars)).wait_until_completed()
        assert job.is_successful

        launch_time_vars = utils.load_json_or_yaml(launch_time_vars)
        job_extra_vars = json.loads(job.extra_vars)

        expected_job_vars = dict(submitter_email=launch_time_vars['submitter_email'])
        assert job_extra_vars == expected_job_vars

    @pytest.mark.ha_tower
    def test_post_spec_with_missing_fields(self, job_template_ping):
        """Verify the API does not allow survey creation when missing any or all
        of the spec, name, or description fields.
        """
        job_template_ping.survey_enabled = True

        missing_field_survey_specs = [dict(),
                                      dict(description=fauxfactory.gen_utf8(),
                                           spec=[dict(required=False,
                                                      question_name="Enter your email &mdash; &euro;",
                                                      variable="submitter_email",
                                                      type="text",)]),
                                      dict(name=fauxfactory.gen_utf8(),
                                           spec=[dict(required=False,
                                                      question_name="Enter your email &mdash; &euro;",
                                                      variable="submitter_email",
                                                      type="text",)]),
                                      dict(name=fauxfactory.gen_utf8(),
                                           description=fauxfactory.gen_utf8()),
                                      dict(name=fauxfactory.gen_utf8(),
                                           description=fauxfactory.gen_utf8(),
                                           spec=[])]

        for spec in missing_field_survey_specs:
            with pytest.raises(exc.BadRequest):
                job_template_ping.related.survey_spec.post(spec)

    @pytest.mark.ha_tower
    def test_post_spec_with_empty_name(self, job_template_ping):
        """Verify the API allows a survey_spec with an empty name and description"""
        job_template_ping.survey_enabled = True
        job_template_ping.related.survey_spec.post(dict(name='',
                                                        description='',
                                                        spec=[dict(required=False,
                                                                   question_name=fauxfactory.gen_utf8(),
                                                                   question_description=fauxfactory.gen_utf8(),
                                                                   variable="submitter_email",
                                                                   type="text")]))

    @pytest.mark.ha_tower
    def test_update_survey_spec(self, job_template_ping, optional_survey_spec, required_survey_spec):
        """Verify the API allows replacing a survey spec with subsequent posts"""
        job_template_ping.add_survey(spec=optional_survey_spec)
        survey_spec = job_template_ping.get_related('survey_spec')
        assert survey_spec.spec == optional_survey_spec

        job_template_ping.add_survey(spec=required_survey_spec)
        survey_spec.get()
        assert survey_spec.spec == required_survey_spec

    @pytest.mark.ha_tower
    def test_job_template_launch_survey_enabled(self, job_template_ping, required_survey_spec):
        """Assess launch_pg.survey_enabled behaves as expected."""
        # check that survey_enabled is false by default
        launch_pg = job_template_ping.get_related("launch")
        assert not launch_pg.survey_enabled, \
            "launch_pg.survey_enabled is True even though JT survey_enabled is False \
            and no survey given."

        # check that survey_enabled is false when enabled on JT but no survey created
        job_template_ping.survey_enabled = True
        launch_pg = job_template_ping.get_related("launch")
        assert not launch_pg.survey_enabled, \
            "launch_pg.survey_enabled is True with JT survey_enabled as True \
            and no survey given."

        # check that survey_enabled is true when enabled on JT and survey created
        job_template_ping.add_survey(spec=required_survey_spec)
        launch_pg = job_template_ping.get_related("launch")
        assert launch_pg.survey_enabled, \
            "launch_pg.survey_enabled is False even though JT survey_enabled is True \
            and valid survey posted."

    @pytest.mark.ha_tower
    def test_launch_with_optional_survey_spec(self, job_template_ping, optional_survey_spec):
        """Verify launch_pg attributes with an optional survey spec and job extra_vars."""
        job_template_ping.add_survey(spec=optional_survey_spec)
        survey = job_template_ping.get_related('survey_spec')

        launch = job_template_ping.get_related('launch')
        assert launch.can_start_without_user_input
        assert launch.variables_needed_to_start == []

        job = job_template_ping.launch().wait_until_completed()
        assert job.is_successful

        job_extra_vars = utils.load_json_or_yaml(job.extra_vars)

        expected_extra_vars = dict()
        for question in survey.spec:
            if question.get('required', False) is False and question.get('default') not in (None, ''):
                expected_extra_vars[question['variable']] = question['default']

        assert set(job_extra_vars) == set(expected_extra_vars)
