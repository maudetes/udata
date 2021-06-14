from flask import Flask
import pytest
import sentry_sdk

from udata import sentry


class SentryTransportMock(sentry_sdk.Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events = []

    def capture_event(
        self, event
    ):
        self.events.append(event)

    def capture_envelope(
        self, envelope
    ):
        pass


@pytest.fixture
def flask():
    flask = Flask(__name__)

    @flask.route('/success')
    def index():
        return 'ok'

    @flask.route('/error')
    def zero_division_error():
        1 / 0
        return 'not ok'
    return flask


@pytest.fixture
def celery_divide_task(celery_app):
    @celery_app.task
    def divide(x, y):
        return x / y

    return divide


@pytest.fixture
def transport_mock(app):
    app.config["SENTRY_DSN"] = "http://1@data.gouv.fr/3"
    t_mock = SentryTransportMock()
    sentry.init_app(app, transport=t_mock)
    return t_mock


class SentryTest:
    def test_flask_sentry_no_event(self, app, flask):
        '''We succesfully call a route, no event should be caught by sentry'''
        
        transport_mock = SentryTransportMock()
        sentry.init_app(app, transport=transport_mock)

        with flask.test_client() as client:
            response = client.get('/success')
            assert not transport_mock.events

    def test_flask_sentry_events(self, app, flask):
        '''We call a route that raises a ZeroDivisionError, event should be caught by sentry'''
        
        transport_mock = SentryTransportMock()
        sentry.init_app(app, transport=transport_mock)
        
        with flask.test_client() as client:
            response = client.get('/error')
            assert len(transport_mock.events) == 1
            assert transport_mock.events[0]['exception']['values'][0]['type'] == 'ZeroDivisionError'
            transport_mock.events[0]['exception']['values'][0]['mechanism']['type'] == 'flask'

    def test_celery_sentry_no_event(self, app, celery_divide_task, celery_worker):
        '''We succesfully call a celery task, no event should be caught by sentry'''

        transport_mock = SentryTransportMock()
        sentry.init_app(app, transport=transport_mock)

        celery_worker.reload()  # TODO: add related issue github?

        celery_divide_task.delay(1, 1).get(timeout=10)
        assert not transport_mock.events

    def test_celery_sentry_event_not_caught(self, app, celery_divide_task, celery_worker):
        '''Celery task ZeroDivisionError should not be caught by sentry because initialized too late
           See: https://docs.sentry.io/platforms/python/guides/celery/
        '''

        app.config["SENTRY_DSN"] = "http://1@data.gouv.fr/3" # TODO: rajouter dans la conf de test

        transport_mock = SentryTransportMock()
        sentry.init_app(app, transport=transport_mock)

        celery_worker.reload()

        try:
            celery_divide_task.delay(1, 0).get(timeout=10)
        except ZeroDivisionError:
            pass

        assert not len(transport_mock.events)

    def test_celery_sentry_event_caught(self, transport_mock, celery_divide_task, celery_worker):
        '''Celery task ZeroDivisionError should be caught by sentry because we initialized it before worker'''

        celery_worker.reload()

        try:
            celery_divide_task.delay(1, 0).get(timeout=10)
        except ZeroDivisionError:
            pass

        assert len(transport_mock.events) == 1
        transport_mock.events[0]['exception']['values'][0]['type'] == 'ZeroDivisionError'
        transport_mock.events[0]['exception']['values'][0]['mechanism']['type'] == 'celery'
