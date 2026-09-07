"""TDD tests for caplog integration.

These tests verify that logprise logs show up in pytest's caplog fixture.
"""

from __future__ import annotations

import logging

from logprise import logger


def test_loguru_logger_captured_in_caplog(caplog):
    """Test that logs from loguru's logger show up in caplog."""
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
    with caplog.at_level(logging.WARNING):
        logger.info("Should not appear")
        logger.warning("Should appear")

    messages = [record.message for record in caplog.records]
    assert not any("Should not appear" in msg for msg in messages)
    assert any("Should appear" in msg for msg in messages)


def test_caplog_records_have_correct_level(caplog):
    """Test that captured records have the correct log level."""
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
    named_logger = logging.getLogger("test.named.logger")

    with caplog.at_level(logging.INFO):
        logger.info("From loguru")
        named_logger.info("From named logger")

    messages = [record.message for record in caplog.records]
    assert any("From loguru" in msg for msg in messages)
    assert any("From named logger" in msg for msg in messages)


def test_records_point_at_the_real_file(caplog):
    """pathname/filename/lineno/funcName come from the call site, not a namedtuple repr."""
    with caplog.at_level(logging.INFO):
        logger.info("where am I")

    record = caplog.records[-1]
    assert record.pathname == __file__
    assert record.filename == "test_caplog_integration.py"
    assert record.funcName == "test_records_point_at_the_real_file"
    assert record.lineno > 0


def test_stdlib_records_keep_their_logger_name(caplog):
    """A record logged on 'myapp.db' is captured once, under that name."""
    with caplog.at_level(logging.INFO):
        logging.getLogger("myapp.db").info("x")

    assert caplog.record_tuples == [("myapp.db", logging.INFO, "x")]


def test_native_loguru_records_carry_the_module_name(caplog):
    with caplog.at_level(logging.INFO):
        logger.info("native")

    assert caplog.record_tuples == [(__name__, logging.INFO, "native")]


def test_non_propagating_logger_is_still_captured(caplog):
    """A logger the host cut off from root never reaches pytest's handler; the bridge covers it."""
    log = logging.getLogger("test.noprop")
    log.propagate = False
    try:
        with caplog.at_level(logging.WARNING):
            log.warning("cut off from root")
    finally:
        log.propagate = True

    assert caplog.record_tuples == [("test.noprop", logging.WARNING, "cut off from root")]


def test_root_logger_record_is_captured_once(caplog):
    """This and the next test each log one root record and must each see exactly one; order used to matter."""
    with caplog.at_level(logging.WARNING):
        logging.warning("one root record")

    assert caplog.record_tuples == [("root", logging.WARNING, "one root record")]


def test_root_logger_record_is_captured_once_again(caplog):
    with caplog.at_level(logging.WARNING):
        logging.warning("another root record")

    assert caplog.record_tuples == [("root", logging.WARNING, "another root record")]


def test_caplog_filtering_applies(caplog):
    with caplog.filtering(logging.Filter("zzz")), caplog.at_level(logging.INFO):
        logging.getLogger("aaa.bbb").info("should be filtered")
        logger.info("native, also filtered")

    assert caplog.records == []


def test_logger_remove_inside_a_test_keeps_capturing(caplog):
    """The README advertises logger.remove(); it must neither break teardown nor hide later records."""
    with caplog.at_level(logging.WARNING):
        logger.remove()
        logger.warning("after remove")

    assert any("after remove" in record.message for record in caplog.records)
