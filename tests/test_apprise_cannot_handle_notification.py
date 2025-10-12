import sys
import threading
from threading import ExceptHookArgs

from apprise import Apprise

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

    Appriser()

    assert sys.excepthook != my_global_exception_hook, "Exception hook was not replaced."

    # Simulate an uncaught exception
    sys.excepthook(ValueError, ValueError("Test exception"), None)

    # Verify send_notification was called
    mock_send.assert_called_once()
    assert my_hook_was_called, "Global exception hook was not called."


def test_uncaught_exception_hook_with_default_existing_hook(mocker):
    """Test that uncaught exceptions trigger immediate notifications."""
    mock_send = mocker.patch.object(Apprise, "notify", side_effect=Exception)

    Appriser()

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

    Appriser()

    assert threading.excepthook != my_global_exception_hook, "Exception hook was not replaced."

    # Simulate an uncaught exception
    threading.excepthook(ExceptHookArgs((ValueError, ValueError("Test exception"), None, None)))

    # Verify send_notification was called
    mock_send.assert_called_once()
    assert my_hook_was_called, "Global exception hook was not called."


def test_uncaught_threading_exception_hook_with_default_existing_hook(mocker):
    """Test that uncaught exceptions trigger immediate notifications."""
    mock_send = mocker.patch.object(Apprise, "notify", side_effect=Exception)

    Appriser()

    # Simulate an uncaught exception
    threading.excepthook(ExceptHookArgs((ValueError, ValueError("Test exception"), None, None)))

    # Verify send_notification was called
    mock_send.assert_called_once()


def test_multiple_apprise_objects_with_non_default_existing_hook(mocker):
    """Test that uncaught exceptions trigger immediate notifications."""
    mock_send = mocker.patch.object(Apprise, "notify", side_effect=Exception)
    _1 = Appriser()
    _2 = Appriser()
    sys.excepthook(ValueError, ValueError("Test exception"), None)
    mock_send.assert_called_once()
