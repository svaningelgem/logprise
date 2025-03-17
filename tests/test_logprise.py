import logging
import re

import pytest
from loguru import logger

from logprise import Appriser, InterceptHandler


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
    assert appriser.buffer[0].record["message"] == test_message
    assert appriser.buffer[0].record["level"].name == "ERROR"


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
    assert all(message.record["level"].no >= logger.level("WARNING").no for message in appriser.buffer)


def test_send_notification(notify_mock, noop):
    """Test the complete flow from logging to notification"""
    appriser = Appriser()
    appriser.add(noop)

    # Generate some logs
    logger.error("Database connection failed")
    logger.critical("System shutdown initiated")

    # Send notification
    appriser.send_notification()

    # Verify notification content
    assert len(notify_mock) == 1
    notification = notify_mock[0]
    assert notification["title"] == "Script Notifications"
    assert re.search(" \| ERROR    \| test_logprise:test_send_notification:\d+ - Database connection failed", notification["body"])
    assert re.search(" \| CRITICAL \| test_logprise:test_send_notification:\d+ - System shutdown initiated", notification["body"])

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
    mocker.patch("apprise.cli.DEFAULT_CONFIG_PATHS", [str(config_path)])

    # Create a temporary config file
    config_path.write_text("urls:\n      - mailto://localhost?from=me@local.be&to=you@local.be")

    appriser = Appriser()
    # If config is loaded successfully, urls will be populated
    assert len(appriser.apprise_obj) == 1


def test_multiple_notification_batching(notify_mock, noop):
    """Test that multiple log messages get batched into single notification"""
    appriser = Appriser()
    appriser.add(noop)

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


def test_notification_level_changes():
    """Test changing notification levels and verifying correct message capture"""
    # Initialize with WARNING level
    appriser = Appriser(apprise_trigger_level="WARNING")

    # First batch: WARNING level
    logger.info("Info message 1")
    logger.warning("Warning message 1")
    logger.error("Error message 1")

    assert len(appriser.buffer) == 2
    assert "Info message 1" not in [message.record["message"] for message in appriser.buffer]
    assert "Warning message 1" in [message.record["message"] for message in appriser.buffer]
    assert "Error message 1" in [message.record["message"] for message in appriser.buffer]

    # Clear buffer
    appriser.buffer.clear()

    # Change to ERROR level
    appriser.notification_level = "ERROR"
    logger.info("Info message 2")
    logger.warning("Warning message 2")

    assert len(appriser.buffer) == 0

    # Change to INFO level
    appriser.notification_level = "INFO"
    logger.info("Info message 3")
    logger.warning("Warning message 3")

    assert len(appriser.buffer) == 2
    assert "Info message 3" in [message.record["message"] for message in appriser.buffer]
    assert "Warning message 3" in [message.record["message"] for message in appriser.buffer]


def test_notification_level_edge_cases():
    """Test edge cases for notification levels"""
    appriser = Appriser()

    # Test setting levels in different formats
    appriser.notification_level = "DEBUG"  # string
    assert appriser.notification_level == logger.level("DEBUG").no

    appriser.notification_level = 30  # int (WARNING level)
    assert appriser.notification_level == logger.level("WARNING").no

    appriser.notification_level = logger.level("ERROR")  # Level object
    assert appriser.notification_level == logger.level("ERROR").no

    # Test invalid level
    with pytest.raises(TypeError):
        appriser.notification_level = None

    with pytest.raises(ValueError):
        appriser.notification_level = "INVALID_LEVEL"


def test_custom_log_level():
    """Test handling of custom log levels that don't map to loguru levels"""
    # Create a custom log level in standard logging
    custom_level_num = 15  # Between DEBUG and INFO
    custom_level_name = "CUSTOM"
    logging.addLevelName(custom_level_num, custom_level_name)

    # Set up standard logger with our custom level
    standard_logger = logging.getLogger("custom_test")
    standard_logger.setLevel(custom_level_num)
    standard_logger.addHandler(InterceptHandler())

    # Create Appriser with low threshold to catch all messages
    appriser = Appriser(apprise_trigger_level="DEBUG")

    # Log using our custom level
    standard_logger.log(custom_level_num, "Custom level message")

    # Verify the message was captured and level was handled appropriately
    assert len(appriser.buffer) == 1
    record = appriser.buffer[0].record
    # The level number should be preserved even if the name isn't in loguru
    assert record["level"].no == custom_level_num


def test_all_standard_levels():
    """Test all standard logging levels are handled correctly"""
    appriser = Appriser(apprise_trigger_level="DEBUG")

    # Dictionary of standard logging levels and their expected loguru equivalents
    standard_levels = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    # Test each standard level
    for level_no, level_name in standard_levels.items():
        logger.log(level_name, f"Test message for {level_name}")

        # Find the corresponding record
        matching_records = [r for r in appriser.buffer if r.record["level"].name == level_name]
        assert len(matching_records) == 1
        assert matching_records[0].record["level"].no == level_no

    # Verify total number of records
    assert len(appriser.buffer) == len(standard_levels)
