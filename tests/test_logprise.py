import logging
from pathlib import Path

import apprise
from loguru import logger

from logprise import InterceptHandler, Appriser


def test_intercept_handler_forwards_to_loguru():
    """Test that standard logging messages get forwarded to loguru"""
    # Configure standard logging to use our handler
    standard_logger = logging.getLogger("test_logger")
    standard_logger.addHandler(InterceptHandler())
    standard_logger.setLevel(logging.DEBUG)

    # Create an Appriser to capture the logs
    appriser = Appriser()

    # Log using standard logging
    test_message = "Test log message"
    standard_logger.error(test_message)

    # Verify the message was captured by our appriser
    assert len(appriser.buffer) == 1
    assert appriser.buffer[0]["message"] == test_message
    assert appriser.buffer[0]["level"].name == "ERROR"


def test_appriser_notification_levels():
    """Test that Appriser respects different notification levels"""
    appriser = Appriser(apprise_trigger_level="WARNING")

    # These should be captured
    logger.warning("Test warning")
    logger.error("Test error")
    logger.critical("Test critical")

    # These should not be captured
    logger.debug("Test debug")
    logger.info("Test info")

    assert len(appriser.buffer) == 3
    assert all(record["level"].no >= logger.level("WARNING").no for record in appriser.buffer)


def test_send_notification(notify_mock):
    """Test the complete flow from logging to notification"""
    appriser = Appriser()

    # Generate some logs
    logger.error("Database connection failed")
    logger.critical("System shutdown initiated")

    # Send notification
    appriser.send_notification()

    # Verify notification content
    assert len(notify_mock) == 1
    notification = notify_mock[0]
    assert notification["title"] == "Script Notifications"
    assert "ERROR: Database connection failed" in notification["body"]
    assert "CRITICAL: System shutdown initiated" in notification["body"]

    # Buffer should be cleared after sending
    assert len(appriser.buffer) == 0


def test_send_notification_empty():
    """Test sending notification with no triggers"""
    appriser = Appriser(apprise_trigger_level="ERROR")

    # Log messages below notification level
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")

    # Nothing should be in buffer
    assert len(appriser.buffer) == 0

    # Send notification (should do nothing)
    appriser.send_notification()
    assert len(appriser.buffer) == 0


def test_config_file_loading(tmp_path, mocker):
    """Test that Appriser can load config from filesystem"""
    # Mock DEFAULT_CONFIG_PATHS to only use our temp directory
    config_path = tmp_path / "apprise.yml"
    mocker.patch('apprise.cli.DEFAULT_CONFIG_PATHS', [str(config_path)])

    # Create a temporary config file
    config_path.write_text("urls:\n      - mailto://localhost?from=me@local.be&to=you@local.be")

    appriser = Appriser()
    # If config is loaded successfully, urls will be populated
    assert len(appriser.apprise_obj) == 1


def test_multiple_notification_batching(notify_mock):
    """Test that multiple log messages get batched into single notification"""
    appriser = Appriser()

    # Generate logs over time
    logger.error("Error 1")
    logger.error("Error 2")
    logger.critical("Critical 1")
    logger.error("Error 3")

    # Send notification
    appriser.send_notification()

    # Should be one notification containing all messages
    assert len(notify_mock) == 1
    notification = notify_mock[0]
    assert "Error 1" in notification["body"]
    assert "Error 2" in notification["body"]
    assert "Critical 1" in notification["body"]
    assert "Error 3" in notification["body"]