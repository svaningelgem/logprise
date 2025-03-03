import sys

import loguru
import loguru._simple_sinks

from logprise import logger


def test_prevent_removal_of_accumulator():
    """Test that Appriser keeps adding its interception"""
    core = logger._core

    assert len(core.handlers) == 1  # 1 because we have a silence-autofixture

    current_id: int = next(iter(core.handlers))
    assert type(core.handlers[current_id]._sink) is loguru._simple_sinks.CallableSink

    old_sink_function = core.handlers[current_id]._sink._function
    assert "bound method Appriser.accumulate_log" in str(old_sink_function)

    logger.remove()  # Means: remove all

    assert len(core.handlers) == 1
    assert current_id not in core.handlers, f"'{current_id}' should have been removed!"
    new_sink_function = core.handlers[current_id + 1]._sink._function
    assert old_sink_function is not new_sink_function
    assert "bound method Appriser.accumulate_log" in str(new_sink_function)


def test_prevent_removal_of_accumulator_not_removing_it():
    """Test that Appriser doesn't meddle in other handlers"""
    core = logger._core

    assert len(core.handlers) == 1  # 1 because we have a silence-autofixture
    accumulator_id: int = next(iter(core.handlers))

    mock_id = logger.add(sys.stderr)
    assert len(core.handlers) == 2

    assert type(core.handlers[accumulator_id]._sink) is loguru._simple_sinks.CallableSink

    old_sink_function = core.handlers[accumulator_id]._sink._function
    assert "bound method Appriser.accumulate_log" in str(old_sink_function)

    logger.remove(mock_id)  # Only remove the mocked handler

    assert len(core.handlers) == 1
    assert accumulator_id in core.handlers  # Nothing should have changed!
