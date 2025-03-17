from typing import Any

import pytest
from apprise import Apprise, NotifyBase, NotifyType

import logprise


class NoOpNotifier(NotifyBase):
    """No-operation notifier that silently discards messages."""

    # Define the default secure protocol
    secure_protocol = False

    # Define protocol(s) this notification supports
    protocol = ("noop", "dummy")

    def __init__(self, **kwargs):
        super().__init__(secure=False, **kwargs)

    def url(self, privacy: bool = False, *args: Any, **kwargs: Any) -> str:
        return "noop://"

    def send(self, body: str, title: str = "", notify_type: NotifyType = NotifyType.INFO, **kwargs: Any) -> bool:
        # Simply return True to simulate successful notification
        return True


@pytest.fixture()
def noop() -> NoOpNotifier:
    return NoOpNotifier()


@pytest.fixture(autouse=True)
def notify_mock(monkeypatch):
    """Only mock the notify method of Apprise"""
    calls = []

    def mock_notify(self, title, body, *_, **__):
        calls.append({"title": title, "body": body})
        return True

    monkeypatch.setattr(Apprise, "notify", mock_notify)
    return calls


@pytest.fixture(autouse=True)
def silence_logger():
    logprise.logger.remove()  # Silence any output
    yield
    logprise.logger.remove()  # And restore any handlers we added
