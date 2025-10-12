import logging

import pytest_mock

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
