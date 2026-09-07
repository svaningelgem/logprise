"""Exception-hook and cleanup behaviour that the hook tests in test_apprise_cannot_handle_notification.py
do not cover: a thread crash must not silence the exit flush, SystemExit in a thread is not an error, a host
excepthook wrapped in functools.partial is still chained, and cleanup() on a never-installed instance leaves
the process hooks alone."""

import functools
import sys
import threading
from threading import ExceptHookArgs

import pytest
from conftest import NoOpNotifier, make_appriser
from loguru import logger

from logprise import Appriser


# pytest's own thread hook (a functools.partial) is the "original" hook here and is now correctly chained,
# so pytest sees the simulated crash and would report it; that report is the expected outcome, not a defect.
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_thread_crash_does_not_silence_the_exit_flush(apprise_noop):
    """A thread excepthook fires mid-process; errors logged afterwards must still reach cleanup()'s send."""
    appriser, noop = apprise_noop

    threading.excepthook(ExceptHookArgs((RuntimeError, RuntimeError("worker died"), None, None)))
    assert len(noop.calls) == 1  # the crash itself is reported immediately

    logger.error("must still be delivered at exit")
    appriser.cleanup()

    assert any("must still be delivered at exit" in call["body"] for call in noop.calls)


def test_sys_exit_in_a_thread_is_not_an_error():
    """threading.excepthook ignores SystemExit; ending a thread with sys.exit() must not page anyone."""
    threading.excepthook = threading.__excepthook__  # the stdlib default as the original: never chained
    appriser = make_appriser()
    noop = NoOpNotifier()
    appriser.add(noop)

    threading.excepthook(ExceptHookArgs((SystemExit, SystemExit(0), None, None)))

    assert appriser.buffer == []
    assert noop.calls == []


def test_host_excepthook_installed_as_partial_is_still_called():
    """A functools.partial has no module of its own; it must not be mistaken for a stdlib hook and skipped."""
    seen = []

    def host_hook(exc_type, exc_value, exc_traceback, *, extra):
        seen.append(extra)

    sys.excepthook = functools.partial(host_hook, extra="x")
    make_appriser()

    sys.excepthook(ValueError, ValueError("boom"), None)

    assert seen == ["x"]


def test_cleanup_on_an_uninstalled_appriser_leaves_the_hooks_alone():
    """cleanup() before install() has nothing to restore and must not overwrite the hooks with None."""
    before = (sys.excepthook, threading.excepthook)

    Appriser().cleanup()

    assert (sys.excepthook, threading.excepthook) == before
