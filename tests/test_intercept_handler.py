import logging

import pytest_mock
from conftest import make_appriser
from loguru import logger

from logprise import InterceptHandler


def test_duplicate_emitted_record(mocker: pytest_mock.MockerFixture):
    handler = InterceptHandler()

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    get_message = mocker.patch.object(record, "getMessage")

    assert not hasattr(record, "_has_been_handled_by_interceptor")

    assert get_message.call_count == 0

    handler.emit(record)

    assert get_message.call_count == 1

    assert hasattr(record, "_has_been_handled_by_interceptor")
    assert record._has_been_handled_by_interceptor is True

    handler.emit(record)

    assert get_message.call_count == 1  # STILL 1!


def test_intercepted_record_points_at_the_stdlib_call_site():
    """loguru's depth must land on the frame that called logging, not two frames above it."""
    make_appriser()
    records: list[dict] = []
    logger.add(lambda message: records.append(message.record), level=0)

    def call_site() -> None:
        logging.getLogger("test.depth").error("where was I called from?")

    call_site()

    assert records[-1]["function"] == "call_site"
    assert records[-1]["name"] == __name__
