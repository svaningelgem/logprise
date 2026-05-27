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


def make_appriser(*, add_noop: bool = False, **kwargs: Any) -> Appriser:
    """Build an Appriser and arm it, exactly as importing the package does.

    Constructing an Appriser only sets up instance-local state; ``install()``
    performs the process-global side effects (logging interception, exception
    hooks, the flush thread). Tests that exercise that behavior need an armed
    instance, so route every construction through this helper.

    Pass ``add_noop=True`` to also configure a NoOpNotifier, for tests that need
    a service present (so ``notify()`` is actually attempted) but don't need a
    handle on it. Tests that need the notifier handle should use the
    ``apprise_noop`` fixture instead.
    """
    appriser = Appriser(**kwargs)
    appriser.install()
    if add_noop:
        appriser.add(NoOpNotifier())
    return appriser


@pytest.fixture
def apprise_noop() -> Generator[tuple[Appriser, NoOpNotifier], Any, None]:
    a = make_appriser()
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
