import base
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException


class Dashboard(base.Base):
    '''FIXME'''
    _tab_title = "Home"
    _activity_stream_button_locator = (By.CSS_SELECTOR, '#stream_btn')
    _job_status_graph_locator = (By.CSS_SELECTOR, '#dash-job-status-graph')
    _host_status_graph_locator = (By.CSS_SELECTOR, '#dash-host-status-graph')
    _jobs_list_locator = (By.CSS_SELECTOR, '#dash-jobs-list')
    _host_count_graph_locator = (By.CSS_SELECTOR, '#dash-host-count-graph')

    @property
    def activity_stream_button(self):
        return self.get_visible_element(*self._activity_stream_button_locator)

    @property
    def has_activity_stream_button(self):
        try:
            return self.activity_stream_button.is_displayed()
        except NoSuchElementException:
            return False

    def click_activity_stream(self):
        self.activity_stream_button.click()
        return Organization_Activity_Page(self.testsetup)

    @property
    def job_status_graph(self):
        return self.get_visible_element(*self._job_status_graph_locator)

    @property
    def has_job_status_graph(self):
        try:
            return self.job_status_graph.is_displayed()
        except NoSuchElementException:
            return False

    @property
    def host_status_graph(self):
        return self.get_visible_element(*self._host_status_graph_locator)

    @property
    def has_host_status_graph(self):
        try:
            return self.host_status_graph.is_displayed()
        except NoSuchElementException:
            return False

    @property
    def jobs_list(self):
        return self.get_visible_element(*self._jobs_list_locator)

    @property
    def has_jobs_list(self):
        try:
            return self.jobs_list.is_displayed()
        except NoSuchElementException:
            return False

    @property
    def host_count_graph(self):
        return self.get_visible_element(*self._host_count_graph_locator)

    @property
    def has_host_count_graph(self):
        try:
            return self.host_count_graph.is_displayed()
        except NoSuchElementException:
            return False

class Dashboard_Activity_Page(base.Base):
    '''fixme'''

