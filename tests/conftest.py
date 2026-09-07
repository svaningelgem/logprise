import atexit
import sys
import threading
from collections.abc import Generator
from typing import Any

import apprise.cli
import pytest
from apprise import NotifyBase, NotifyType

from logprise import Appriser, logger
from logprise._sinks import unprotect


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
    _armed.append(appriser)
    if add_noop:
        appriser.add(NoOpNotifier())
    return appriser


# Every instance make_appriser() armed during the current test; disposed of on teardown.
_armed: list[Appriser] = []


def dispose(appriser: Appriser) -> None:
    """Disarm an instance ``make_appriser()`` built: stop its flush thread and drop its atexit hook.

    ``install()`` starts a daemon flush thread and registers ``cleanup`` with ``atexit``.
    Left alone, every instance a test built keeps flushing for the rest of the session and
    fires its own delivery attempt at interpreter exit.
    """
    appriser.stop_periodic_flush()
    atexit.unregister(appriser.cleanup)
    unprotect(appriser.accumulate_log)  # its accumulator would otherwise outlive the test


@pytest.fixture(scope="session", autouse=True)
def no_host_apprise_config() -> Generator[None, None, None]:
    """Never load the developer's real apprise config (``~/.apprise`` etc.) into test instances.

    ``install()`` calls ``_load_default_config_paths``; with a real config present every
    ``make_appriser()`` instance gains real targets, which breaks the tests that count
    services or notify() calls and makes the leaked instances page the developer at exit.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(apprise.cli, "DEFAULT_CONFIG_PATHS", [])
        yield


@pytest.fixture(autouse=True)
def dispose_armed_apprisers() -> Generator[None, None, None]:
    try:
        yield
    finally:
        instances, _armed[:] = list(_armed), []
        for instance in instances:
            dispose(instance)


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
