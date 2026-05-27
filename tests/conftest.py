import sys
import threading
from collections.abc import Generator
from typing import Any

import pytest
from apprise import NotifyBase, NotifyType

from logprise import Appriser, logger


class NoOpNotifier(NotifyBase):
    """No-operation notifier that silently discards messages."""

    # Define the default secure protocol
    secure_protocol = False

    # Define protocol(s) this notification supports
    protocol = ("noop", "dummy")

    calls: list[dict]

    def __init__(self, **kwargs):
        super().__init__(secure=False, **kwargs)
        self.calls = []

    def url(self, privacy: bool = False, *args: Any, **kwargs: Any) -> str:
        return "noop://"

    def send(self, body: str, title: str = "", notify_type: NotifyType = NotifyType.INFO, **kwargs: Any) -> bool:
        # Simply return True to simulate successful notification
        self.calls.append({"title": title, "body": body})
        return True


@pytest.fixture
def apprise_noop() -> Generator[tuple[Appriser, NoOpNotifier], Any, None]:
    a = Appriser()
    noop = NoOpNotifier()
    a.add(noop)
    try:
        yield a, noop
    finally:
        a.cleanup()


@pytest.fixture(autouse=True)
def reset_appriser_object() -> Generator[None, None, None]:
    try:
        yield
    finally:
        Appriser._exit_via_unhandled_exception = False


@pytest.fixture(autouse=True)
def save_restore_excepthooks() -> Generator[None, None, None]:
    original_excepthook = sys.excepthook
    original_threading_excepthook = threading.excepthook
    try:
        yield
    finally:
        sys.excepthook = original_excepthook
        threading.excepthook = original_threading_excepthook


@pytest.fixture(autouse=True)
def silence_logger():
    logger.remove()  # Silence any output
    try:
        yield
    finally:
        logger.remove()  # And restore any handlers we added
