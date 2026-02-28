"""Pytest plugin for logprise/caplog integration.

This plugin ensures that logs emitted via logprise (which uses loguru internally)
are captured by pytest's caplog fixture.

The plugin is automatically loaded by pytest when logprise is installed,
thanks to the pytest11 entry point defined in pyproject.toml.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from loguru import logger


if TYPE_CHECKING:
    from collections.abc import Generator

    from _pytest.logging import LogCaptureFixture


class _CaplogState:
    """Container for caplog fixture state to avoid module-level globals."""

    fixture: LogCaptureFixture | None = None


_state = _CaplogState()


def _create_log_record(record: dict) -> logging.LogRecord:
    """Create a standard logging.LogRecord from a loguru record dict."""
    # Get the level info
    level_no = record["level"].no
    level_name = record["level"].name

    # Get module/function info
    module = record.get("module", "")
    func_name = record.get("function", "")
    line_no = record.get("line", 0)
    file_path = record.get("file", None)
    pathname = str(file_path) if file_path else ""

    # Create a LogRecord directly
    log_record = logging.LogRecord(
        name=record.get("name") or module or "logprise",
        level=level_no,
        pathname=pathname,
        lineno=line_no,
        msg=record["message"],
        args=(),
        exc_info=record["exception"],
        func=func_name,
    )

    # Set the level name explicitly
    log_record.levelname = level_name

    return log_record


def _loguru_to_caplog(message: object) -> None:
    """Sink function that forwards loguru messages directly to caplog's handler.

    This function bypasses the standard logging system entirely to avoid
    the recursion caused by logprise's InterceptHandler.
    """
    if _state.fixture is None:
        return

    # Get the record dict from the message
    record = message.record  # type: ignore[union-attr]

    # Create a standard LogRecord
    log_record = _create_log_record(record)

    # Check if the record's level meets the caplog's handler level threshold
    # This respects caplog.at_level() context manager
    if log_record.levelno >= _state.fixture.handler.level:
        _state.fixture.handler.emit(log_record)


@pytest.fixture
def caplog(caplog: LogCaptureFixture) -> Generator[LogCaptureFixture, None, None]:
    """Enhanced caplog fixture that captures logprise/loguru logs.

    This fixture wraps pytest's built-in caplog fixture and adds a loguru
    sink that forwards logs directly to caplog's handler, bypassing
    the standard logging system to avoid recursion with logprise's
    InterceptHandler.
    """
    # Store reference to caplog fixture
    _state.fixture = caplog

    # Add a loguru sink that writes directly to caplog
    handler_id = logger.add(
        _loguru_to_caplog,
        format="{message}",
        level=0,  # Capture all levels, let caplog filter
        catch=False,
    )

    try:
        yield caplog
    finally:
        # Remove the sink and clear the fixture reference
        logger.remove(handler_id)
        _state.fixture = None
