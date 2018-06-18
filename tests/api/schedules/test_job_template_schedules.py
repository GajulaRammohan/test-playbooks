import json

from towerkit import utils
from towerkit import exceptions as exc
import pytest

from tests.api.schedules import SchedulesTest


@pytest.mark.api
@pytest.mark.usefixtures('authtoken', 'install_enterprise_license_unlimited')
@pytest.mark.saved_prompts
class TestJobTemplateSchedules(SchedulesTest):

    select_jt_fields = ('inventory', 'credential', 'project', 'playbook', 'job_type', 'job_tags', 'skip_tags',
                        'verbosity', 'diff_mode', 'limit')

    def ask_everything(self, setup=False, inventory=None, config=False):
        r = {}
        # names for promptable fields and a non-default value
        prompts = [
                ('variables', {'var1': 'bar'}),
                ('diff_mode', True),
                ('limit', 'test_limit'),
                ('tags', 'test_tag'),
                ('skip_tags', 'test_skip_tag'),
                ('job_type', 'check'),
                ('verbosity', 5),
                ('inventory', inventory.id if inventory else None)
        ]
        for fd, val in prompts:
            if setup:
                r['ask_{}_on_launch'.format(fd)] = True
            else:
                job_fd = fd
                if fd == 'tags':
                    job_fd = 'job_tags'
                if fd == 'variables':
                    if config:
                        job_fd = 'extra_data'
                    else:
                        job_fd = 'extra_vars'
                r[job_fd] = val
        return r

    def test_schedule_uses_prompted_fields(self, factories, inventory):
        jt = factories.v2_job_template(**self.ask_everything(setup=True))
        schedule = jt.add_schedule(
            rrule=self.minutely_rrule(),
            **self.ask_everything(inventory=inventory, config=True)
        )
        # sanity assertions
        bad_params = []
        for fd, val in self.ask_everything(inventory=inventory, config=True).items():
            if getattr(schedule, fd) != val:
                bad_params.append((fd, val, getattr(schedule, fd)))
        assert not bad_params, 'Schedule parameters {} were not enabled.'.format(bad_params)

        unified_jobs = schedule.related.unified_jobs.get()
        utils.poll_until(lambda: unified_jobs.get().count == 1, interval=15, timeout=1.5 * 60)
        job = unified_jobs.results.pop()
        assert job.wait_until_completed().is_successful
        job_values = []
        for fd, val in self.ask_everything(inventory=inventory).items():
            job_val = getattr(job, fd)
            if fd == 'extra_vars':
                job_val = json.loads(job_val)
            if job_val != val:
                job_values.append((fd, val, job_val))
        assert not job_values, 'Job did not use prompts from schedule {}'.format(
            job_values
        )

    def test_schedule_unprompted_fields(self, factories, inventory):
        jt = factories.v2_job_template()
        mrrule = self.minutely_rrule()
        schedule_prompts = self.ask_everything(inventory=inventory, config=True)
        for key, value in schedule_prompts.items():
            data = {}
            data[key] = value
            with pytest.raises(exc.BadRequest) as e:
                jt.add_schedule(rrule=mrrule, **data)
            msg = 'Field is not configured to prompt on launch.'
            if key == 'extra_data':
                msg = ('Variables {} are not allowed on launch. Check the Prompt '
                       'on Launch setting on the Job Template to include Extra Variables.'.format(
                            schedule_prompts['extra_data'].keys()[0]))
            assert e.value[1] == {key: [msg]}

    def test_schedule_jobs_should_source_from_underlying_template(self, factories):
        jt = factories.v2_job_template()
        factories.v2_host(inventory=jt.ds.inventory)

        survey = [dict(required=False,
                       question_name='Q1',
                       variable='var1',
                       type='text',
                       default='survey'),
                  dict(required=False,
                       question_name='Q2',
                       variable='var2',
                       type='password',
                       default='survey')]
        jt.add_survey(spec=survey)
        schedule = jt.add_schedule(rrule=self.minutely_rrule())
        unified_jobs = schedule.related.unified_jobs.get()

        utils.poll_until(lambda: unified_jobs.get().count == 1, timeout=2 * 60)
        job = unified_jobs.results.pop()
        assert job.wait_until_completed().is_successful
        assert json.loads(job.extra_vars) == {'var1': 'survey', 'var2': '$encrypted$'}

        for field in self.select_jt_fields:
            assert getattr(jt, field) == getattr(job, field)

    def test_schedule_values_take_precedence_over_jt_values(self, factories, ask_everything_jt):
        host, credential = factories.v2_host(), factories.v2_credential()

        survey = [dict(required=False,
                       question_name='Q1',
                       variable='var1',
                       type='text',
                       default='survey'),
                  dict(required=False,
                       question_name='Q2',
                       variable='var2',
                       type='password',
                       default='survey')]
        ask_everything_jt.add_survey(spec=survey)
        schedule = ask_everything_jt.add_schedule(rrule=self.minutely_rrule(), inventory=host.ds.inventory, job_type='check',
                                                  limit='all', extra_data={'var1': 'schedule', 'var2': 'schedule'})
        unified_jobs = schedule.related.unified_jobs.get()

        utils.poll_until(lambda: unified_jobs.get().count == 1, timeout=2 * 60)
        job = unified_jobs.results.pop()
        assert job.wait_until_completed().is_successful
        assert json.loads(job.extra_vars) == {'var1': 'survey', 'var2': '$encrypted$'}

        for field in self.select_jt_fields:
            assert getattr(ask_everything_jt, field) == getattr(job, field)

    @pytest.mark.parametrize('ujt_type', ['job_template', 'workflow_job_template'])
    def test_cannot_create_schedule_without_answering_required_survey_questions(self, factories, ujt_type):
        template = getattr(factories, 'v2_' + ujt_type)()
        survey = [dict(required=True,
                       question_name='Q1',
                       variable='var1',
                       type='text',
                       default=''),
                  dict(required=True,
                       question_name='Q2',
                       variable='var2',
                       type='password',
                       defautl='')]
        template.add_survey(spec=survey)
        with pytest.raises(exc.BadRequest) as e:
            template.add_schedule(rrule=self.minutely_rrule())
        assert e.value[1] == e.value[1] == {'variables_needed_to_start': ["'var1' value missing", "'var2' value missing"]}

    @pytest.mark.github('https://github.com/ansible/tower/issues/2182')
    @pytest.mark.parametrize('ujt_type', ['job_template', 'workflow_job_template'])
    def test_can_create_schedule_when_required_survey_questions_answered(self, factories, ujt_type):
        template = getattr(factories, 'v2_' + ujt_type)()
        survey = [dict(required=True,
                       question_name='Q1',
                       variable='var1',
                       type='text',
                       default=''),
                  dict(required=True,
                       question_name='Q2',
                       variable='var2',
                       type='password',
                       default='')]
        template.add_survey(spec=survey)
        schedule = template.add_schedule(rrule=self.minutely_rrule(), extra_data={'var1': 'var1', 'var2': 'very_secret'})
        assert schedule.extra_data == {'var1': 'var1', 'var2': '$encrypted$'}

        unified_jobs = schedule.related.unified_jobs.get()
        utils.poll_until(lambda: unified_jobs.get().count == 1, interval=5, timeout=2 * 60)
        job = unified_jobs.results.pop()
        assert job.wait_until_completed().is_successful
        assert json.loads(job.extra_vars) == {'var1': 'var1', 'var2': '$encrypted$'}

    @pytest.mark.parametrize('ujt_type', ['job_template', 'workflow_job_template'])
    def test_can_create_schedule_when_optional_survey_questions_are_unanswered(self, factories, ujt_type):
        template = getattr(factories, 'v2_' + ujt_type)()
        survey = [dict(required=False,
                       question_name='Q1',
                       variable='var1',
                       type='text',
                       default='var1'),
                  dict(required=False,
                       question_name='Q2',
                       variable='var2',
                       type='password',
                       default='var2')]
        template.add_survey(spec=survey)
        schedule = template.add_schedule(rrule=self.minutely_rrule())
        assert schedule.extra_data == {}

        # test that resultant job has the survey defaults
        unified_jobs = schedule.related.unified_jobs.get()
        utils.poll_until(lambda: unified_jobs.get().count == 1, interval=5, timeout=2 * 60)
        job = unified_jobs.results.pop()
        assert job.wait_until_completed().is_successful
        assert json.loads(job.extra_vars) == {'var1': 'var1', 'var2': '$encrypted$'}

    @pytest.mark.github('https://github.com/ansible/tower/issues/2186')
    @pytest.mark.parametrize('ujt_type', ['job_template', 'workflow_job_template'])
    def test_can_create_schedule_when_defaults_are_supplied_with_required_survey_questions_with_defaults(self, factories,
                                                                                                         ujt_type):
        template = getattr(factories, 'v2_' + ujt_type)()
        survey = [dict(required=True,
                       question_name='Q1',
                       variable='var1',
                       type='text',
                       default='var1'),
                  dict(required=True,
                       question_name='Q2',
                       variable='var2',
                       type='password',
                       default='very_secret')]
        template.add_survey(spec=survey)
        schedule = template.add_schedule(rrule=self.minutely_rrule(), extra_data={'var1': 'var1', 'var2': '$encrypted$'})
        assert schedule.extra_data == {'var1': 'var1'}

        unified_jobs = schedule.related.unified_jobs.get()
        utils.poll_until(lambda: unified_jobs.get().count == 1, interval=5, timeout=2 * 60)
        job = unified_jobs.results.pop()
        assert job.wait_until_completed().is_successful
        assert json.loads(job.extra_vars) == {'var1': 'var1', 'var2': '$encrypted$'}
