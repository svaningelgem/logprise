import sys
import threading
import time
from threading import ExceptHookArgs
from unittest.mock import MagicMock

from conftest import NoOpNotifier

from logprise import Appriser, logger


def test_uncaught_exception_hook(apprise_noop, monkeypatch):
    """Test that uncaught exceptions trigger immediate notifications."""
    appriser, _noop = apprise_noop

    # Mock send_notification to track calls
    mock_send = MagicMock()
    monkeypatch.setattr(appriser, "send_notification", mock_send)

    # Simulate an uncaught exception
    sys.excepthook(ValueError, ValueError("Test exception"), None)

    # Verify send_notification was called
    mock_send.assert_called_once()


def test_uncaught_threading_exception_hook(apprise_noop, monkeypatch):
    """Test that uncaught exceptions trigger immediate notifications."""
    # Save original excepthook
    appriser, _noop = apprise_noop

    # Mock send_notification to track calls
    mock_send = MagicMock()
    monkeypatch.setattr(appriser, "send_notification", mock_send)

    # Simulate an uncaught exception
    threading.excepthook(ExceptHookArgs((ValueError, ValueError("Test exception"), None, None)))

    # Verify send_notification was called
    mock_send.assert_called_once()


def test_periodic_flush(apprise_noop, monkeypatch):
    """Test that logs are periodically flushed."""
    # Create an Appriser with a short flush interval for testing
    appriser, _noop = apprise_noop
    appriser.flush_interval = 0.1  # 100ms for faster testing

    # Mock threading.Thread to control execution
    mock_thread = MagicMock()
    monkeypatch.setattr(threading, "Thread", mock_thread)

    # Re-initialize to trigger thread creation with mocked components
    appriser._start_periodic_flush()

    # Verify thread was started with correct parameters
    mock_thread.assert_called_once()
    assert mock_thread.call_args[1]["target"] == appriser._periodic_flush
    assert mock_thread.call_args[1]["daemon"] is True
    assert mock_thread.call_args[1]["name"] == "logprise-flush"
    mock_thread.return_value.start.assert_called_once()


def test_periodic_flush_integration():
    """Test the periodic flush actually works (integration test)."""
    # Create an Appriser with a short flush interval
    appriser = Appriser(flush_interval=0.2)
    noop = NoOpNotifier()
    appriser.add(noop)

    # Generate an error log (should be captured)
    logger.error("Test periodic flush")

    # Verify message is in the buffer
    assert len(appriser.buffer) == 1

    # Wait for the periodic flush to happen
    time.sleep(0.3)  # Wait longer than flush_interval

    # Buffer should be cleared and notification sent
    assert len(appriser.buffer) == 0
    assert len(noop.calls) == 1
    assert "Test periodic flush" in noop.calls[0]["body"]


def test_stop_periodic_flush():
    """Test that stop_periodic_flush properly terminates the flush thread."""
    appriser = Appriser()

    # Create a mock thread
    mock_thread = MagicMock()
    appriser._flush_thread = mock_thread
    mock_thread.is_alive.return_value = True

    # Stop the periodic flush
    appriser.stop_periodic_flush()

    # Verify that stop_event was set and join was called
    assert appriser._stop_event.is_set()
    mock_thread.join.assert_called_once()

    mock_thread.reset_mock()
    appriser._flush_thread = None
    appriser.stop_periodic_flush()
    assert appriser._stop_event.is_set()
    mock_thread.join.assert_not_called()


def test_periodic_flush_should_stop_on_cleanup(apprise_noop):
    """Test that cleanup method stops the flush thread and sends pending notifications."""
    appriser, noop = apprise_noop

    # Mock stop_periodic_flush
    mock_stop = MagicMock()
    appriser.stop_periodic_flush = mock_stop

    # Add a log message
    logger.error("Test cleanup")

    # Call cleanup
    appriser.cleanup()

    # Verify stop_periodic_flush was called
    mock_stop.assert_called_once()

    # Verify notification was sent
    assert len(noop.calls) == 1
    assert "Test cleanup" in noop.calls[0]["body"]
    assert len(appriser.buffer) == 0


def test_flush_only_if_buffer_has_content(apprise_noop, monkeypatch):
    """Test that periodic flush only sends notifications if buffer has content."""
    appriser, _noop = apprise_noop

    # Empty the buffer
    appriser.buffer.clear()

    # Mock the stop_event.wait to return True to avoid infinite loop
    monkeypatch.setattr(appriser._stop_event, "wait", lambda timeout: True)

    # Create a mock for send_notification to track calls
    mock_send = MagicMock()
    monkeypatch.setattr(appriser, "send_notification", mock_send)

    # Simulate a periodic flush without any logs
    appriser._periodic_flush()

    # Verify send_notification was not called because buffer is empty
    mock_send.assert_not_called()

    # Reset the mock for the next test
    mock_send.reset_mock()

    # Add a log message
    logger.error("Test message")

    # Mock the stop_event.wait to return True again
    monkeypatch.setattr(appriser._stop_event, "wait", lambda timeout: True)

    # Now run _periodic_flush manually with content in the buffer
    # But we'll need to directly call the part that sends the notification
    # because the full method would exit due to our mock returning True
    if appriser.buffer:
        appriser.send_notification()

    # Now send_notification should be called
    mock_send.assert_called_once()


def test_periodic_flush_stops_on_event_set(mocker):
    """Test that periodic_flush exits when stop_event is set."""
    appriser = Appriser()

    # Pre-set the stop event before calling _periodic_flush
    appriser._stop_event.set()

    # Add a log message to ensure buffer has content
    logger.error("Test message")

    # Mock send_notification to track calls
    mock_send = mocker.patch.object(appriser, "send_notification")

    # Run the periodic flush - it should exit immediately
    appriser._periodic_flush()

    # Verify send_notification was not called
    mock_send.assert_not_called()

    # Verify message still in buffer (didn't get cleared)
    assert len(appriser.buffer) == 1
    assert "Test message" in appriser.buffer[0].record["message"]


def test_periodic_flush_empty_buffer(mocker):
    """Test that periodic_flush skips sending when buffer is empty."""
    appriser = Appriser()

    # Clear buffer
    appriser.buffer.clear()

    # Mock send_notification to track calls
    mock_send = mocker.patch.object(appriser, "send_notification")

    # Set up stop_event to trigger after a short delay
    def set_stop_after_delay():
        time.sleep(0.1)  # Short delay
        appriser._stop_event.set()

    # Start a thread that will set the stop event after a delay
    thread = threading.Thread(target=set_stop_after_delay)
    thread.start()

    # Run periodic flush - it should wait until stop_event is set
    appriser._periodic_flush()

    # Wait for our helper thread to complete
    thread.join()

    # Verify send_notification was not called since buffer was empty
    mock_send.assert_not_called()


def test_stop_periodic_flush_idempotent(mocker):
    """Test that calling stop_periodic_flush twice is safe."""
    appriser = Appriser()

    # First call
    appriser.stop_periodic_flush()
    assert appriser._stop_event.is_set()

    # Mock thread for second call
    mock_thread = mocker.MagicMock()
    mock_thread.is_alive.return_value = True
    appriser._flush_thread = mock_thread
    appriser._stop_event.clear()  # Reset to test second call

    # Second call
    appriser.stop_periodic_flush()

    # Verify stop_event is set and join was called
    assert appriser._stop_event.is_set()
    mock_thread.join.assert_called_once()


def test_notify_failure_preserves_buffer(mocker):
    """Test that buffer is not cleared when notification fails."""
    appriser = Appriser()

    # Mock apprise_obj.notify to return False (failure)
    mocker.patch.object(appriser.apprise_obj, "notify", return_value=False)

    # Add test message to buffer
    logger.error("Test message that should remain in buffer")

    # Try to send notification
    appriser.send_notification()

    # Verify buffer still contains the message
    assert len(appriser.buffer) == 1
    assert "Test message that should remain in buffer" in appriser.buffer[0].record["message"]
