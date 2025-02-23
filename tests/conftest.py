import pytest
from apprise import Apprise


@pytest.fixture
def notify_mock(monkeypatch):
    """Only mock the notify method of Apprise"""
    calls = []

    def mock_notify(self, title, body):
        calls.append({"title": title, "body": body})
        return True

    monkeypatch.setattr(Apprise, "notify", mock_notify)
    return calls