"""Pytest plugin: make loguru output visible to pytest's log capture.

logprise routes every record through loguru, and loguru bypasses ``logging``
entirely, so neither pytest's ``caplog`` fixture nor the "Captured log call"
section of a failure report would see anything on their own. This plugin adds
one session-wide loguru sink that hands each message to the root logger's
handlers, which is exactly where pytest installs its capture handlers for
every test phase. Standard-library records that logprise intercepted are
skipped when they still propagate to the root logger, because pytest already
captured the original there with the right name, path and filters applied.

The plugin is loaded automatically by pytest when logprise is installed,
thanks to the pytest11 entry point defined in pyproject.toml.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import pytest

from logprise import _protect_sink, _unprotect_sink, appriser


if TYPE_CHECKING:
    from collections.abc import Generator
    from logging import _SysExcInfoType

    import loguru


class _ForwardedRecord(logging.LogRecord):
    """A LogRecord built from a loguru message.

    The class attribute is the marker InterceptHandler checks, so handing the
    record to the root logger never forwards it back into loguru.
    """

    _has_been_handled_by_interceptor = True


def _to_log_record(record: loguru.Record) -> logging.LogRecord:
    """Build a standard LogRecord from a loguru record dict.

    A record that came in through logprise's interception keeps the name of the
    ``logging`` logger it was logged on; a native loguru call gets the module
    name loguru recorded.
    """
    log_record = _ForwardedRecord(
        name=record["extra"].get("_stdlib_logger") or record["name"] or "logprise",
        level=record["level"].no,
        pathname=record["file"].path,
        lineno=record["line"],
        msg=record["message"],
        args=(),
        exc_info=cast("_SysExcInfoType | None", record["exception"]),
        func=record["function"],
    )
    log_record.levelname = record["level"].name
    return log_record


def _reaches_root(logger_name: str) -> bool:
    """Whether a ``logging`` record from this logger propagates up to the root logger's handlers."""
    root = logging.getLogger()
    current = root if logger_name == "root" else logging.getLogger(logger_name)
    chain: list[logging.Logger] = []
    while current is not root:
        chain.append(current)
        current = current.parent or root
    return all(ancestor.propagate for ancestor in chain)


def _hand_to_root_handlers(message: loguru.Message) -> None:
    """Session-wide loguru sink feeding pytest's capture handlers on the root logger."""
    record = message.record
    stdlib_logger = record["extra"].get("_stdlib_logger")
    if stdlib_logger is not None and _reaches_root(stdlib_logger):
        return  # pytest's handlers on the root logger already captured the original record

    root = logging.getLogger()
    if root.isEnabledFor(record["level"].no):
        root.handle(_to_log_record(record))


def pytest_configure(config: pytest.Config) -> None:
    _protect_sink(_hand_to_root_handlers, level=0)


def pytest_unconfigure(config: pytest.Config) -> None:
    _unprotect_sink(_hand_to_root_handlers)


@pytest.fixture(autouse=True)
def _clear_appriser_buffer() -> Generator[None, None, None]:
    """Hand every test an empty appriser buffer, and release it on teardown.

    Errors emitted during a test (``logger.error(...)`` etc.) accumulate in
    ``appriser.buffer``. Without this fixture, ``atexit`` would later fire
    :meth:`Appriser.cleanup`, which flushes that buffer to whatever real apprise
    services the developer has configured -- so a green test run still pages /
    mails them with every intentionally-exercised error path.

    Mirroring the ``caplog`` fixture's "set up, yield, release in ``finally``"
    shape, autouse so every test (caplog or not) owns the buffer for its
    duration: cleared on the way in so the test starts clean (the first test
    would otherwise inherit whatever buffered during collection / plugin load),
    cleared again on teardown so atexit's :meth:`Appriser.cleanup` sees nothing
    to flush. What happens before pytest starts or after pytest returns is the
    user's domain; inside the session, we leave no buffered records behind.
    """
    appriser.buffer.clear()
    try:
        yield
    finally:
        appriser.buffer.clear()
