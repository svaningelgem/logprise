"""TDD tests for caplog integration.

These tests verify that logprise logs show up in pytest's caplog fixture.
"""

from __future__ import annotations

import logging


def test_loguru_logger_captured_in_caplog(caplog):
    """Test that logs from loguru's logger show up in caplog."""
    from logprise import logger

    with caplog.at_level(logging.INFO):
        logger.info("Test message from loguru")

    assert len(caplog.records) >= 1
    assert any("Test message from loguru" in record.message for record in caplog.records)


def test_standard_logging_captured_in_caplog(caplog):
    """Test that standard logging (intercepted by logprise) shows up in caplog."""
    with caplog.at_level(logging.WARNING):
        logging.warning("Test warning from standard logging")

    assert len(caplog.records) >= 1
    assert any("Test warning from standard logging" in record.message for record in caplog.records)


def test_loguru_different_levels_captured(caplog):
    """Test that different log levels are captured correctly."""
    from logprise import logger

    with caplog.at_level(logging.DEBUG):
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

    messages = [record.message for record in caplog.records]
    assert any("Debug message" in msg for msg in messages)
    assert any("Info message" in msg for msg in messages)
    assert any("Warning message" in msg for msg in messages)
    assert any("Error message" in msg for msg in messages)


def test_caplog_level_filtering(caplog):
    """Test that caplog level filtering works with logprise."""
    from logprise import logger

    with caplog.at_level(logging.WARNING):
        logger.info("Should not appear")
        logger.warning("Should appear")

    messages = [record.message for record in caplog.records]
    assert not any("Should not appear" in msg for msg in messages)
    assert any("Should appear" in msg for msg in messages)


def test_caplog_records_have_correct_level(caplog):
    """Test that captured records have the correct log level."""
    from logprise import logger

    with caplog.at_level(logging.DEBUG):
        logger.warning("Warning test")
        logger.error("Error test")

    warning_records = [r for r in caplog.records if "Warning test" in r.message]
    error_records = [r for r in caplog.records if "Error test" in r.message]

    assert len(warning_records) >= 1
    assert len(error_records) >= 1
    assert warning_records[0].levelno == logging.WARNING
    assert error_records[0].levelno == logging.ERROR


def test_caplog_clear_works(caplog):
    """Test that caplog.clear() works properly."""
    from logprise import logger

    with caplog.at_level(logging.INFO):
        logger.info("First message")
        assert len(caplog.records) >= 1

        caplog.clear()
        assert len(caplog.records) == 0

        logger.info("Second message")
        assert len(caplog.records) >= 1
        messages = [r.message for r in caplog.records]
        assert not any("First message" in msg for msg in messages)
        assert any("Second message" in msg for msg in messages)


def test_multiple_loggers_captured(caplog):
    """Test that logs from multiple loggers are captured."""
    from logprise import logger

    named_logger = logging.getLogger("test.named.logger")

    with caplog.at_level(logging.INFO):
        logger.info("From loguru")
        named_logger.info("From named logger")

    messages = [record.message for record in caplog.records]
    assert any("From loguru" in msg for msg in messages)
    assert any("From named logger" in msg for msg in messages)
