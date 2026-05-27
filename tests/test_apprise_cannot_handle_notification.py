import sys
import threading
from threading import ExceptHookArgs

from apprise import Apprise
from conftest import NoOpNotifier

from logprise import Appriser


def test_uncaught_exception_hook_with_non_default_existing_hook(mocker):
    """Test that uncaught exceptions trigger immediate notifications."""
    mock_send = mocker.patch.object(Apprise, "notify", side_effect=Exception)

    my_hook_was_called = False

    def my_global_exception_hook(_, __, ___):
        nonlocal my_hook_was_called
        my_hook_was_called = True

    sys.excepthook = my_global_exception_hook

    assert sys.excepthook == my_global_exception_hook

    appriser = Appriser()
    appriser.add(NoOpNotifier())  # a service must be configured for notify() to be attempted

    assert sys.excepthook != my_global_exception_hook, "Exception hook was not replaced."

    # Simulate an uncaught exception
    sys.excepthook(ValueError, ValueError("Test exception"), None)

    # Verify send_notification was called
    mock_send.assert_called_once()
    assert my_hook_was_called, "Global exception hook was not called."


def test_uncaught_exception_hook_with_default_existing_hook(mocker):
    """Test that uncaught exceptions trigger immediate notifications."""
    mock_send = mocker.patch.object(Apprise, "notify", side_effect=Exception)

    appriser = Appriser()
    appriser.add(NoOpNotifier())  # a service must be configured for notify() to be attempted

    # Simulate an uncaught exception
    sys.excepthook(ValueError, ValueError("Test exception"), None)

    # Verify send_notification was called
    mock_send.assert_called_once()


def test_uncaught_threading_exception_hook_with_non_default_existing_hook(mocker):
    """Test that uncaught exceptions trigger immediate notifications."""
    mock_send = mocker.patch.object(Apprise, "notify", side_effect=Exception)

    my_hook_was_called = False

    def my_global_exception_hook(_: ExceptHookArgs):
        nonlocal my_hook_was_called
        my_hook_was_called = True

    threading.excepthook = my_global_exception_hook

    assert threading.excepthook == my_global_exception_hook

    appriser = Appriser()
    appriser.add(NoOpNotifier())  # a service must be configured for notify() to be attempted

    assert threading.excepthook != my_global_exception_hook, "Exception hook was not replaced."

    # Simulate an uncaught exception
    threading.excepthook(ExceptHookArgs((ValueError, ValueError("Test exception"), None, None)))

    # Verify send_notification was called
    mock_send.assert_called_once()
    assert my_hook_was_called, "Global exception hook was not called."


def test_uncaught_threading_exception_hook_with_default_existing_hook(mocker):
    """Test that uncaught exceptions trigger immediate notifications."""
    mock_send = mocker.patch.object(Apprise, "notify", side_effect=Exception)

    appriser = Appriser()
    appriser.add(NoOpNotifier())  # a service must be configured for notify() to be attempted

    # Simulate an uncaught exception
    threading.excepthook(ExceptHookArgs((ValueError, ValueError("Test exception"), None, None)))

    # Verify send_notification was called
    mock_send.assert_called_once()


def test_multiple_apprise_objects_with_non_default_existing_hook(mocker):
    """Test that uncaught exceptions trigger immediate notifications."""
    mock_send = mocker.patch.object(Apprise, "notify", side_effect=Exception)
    _1 = Appriser()
    _1.add(NoOpNotifier())  # a service must be configured for notify() to be attempted
    _2 = Appriser()
    _2.add(NoOpNotifier())
    sys.excepthook(ValueError, ValueError("Test exception"), None)
    mock_send.assert_called_once()
