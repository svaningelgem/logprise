import sys

import loguru
import loguru._simple_sinks
from conftest import make_appriser

from logprise import Appriser, _protected_sinks, appriser, logger


def _accumulator_handler_id(instance: Appriser) -> int:
    handler_id, _ = _protected_sinks[instance.accumulate_log]
    return handler_id


def test_prevent_removal_of_accumulator():
    """Test that Appriser keeps adding its interception"""
    core = logger._core

    # The silence autofixture removed everything, so what is left is exactly the protected sinks:
    # one accumulator per installed Appriser, plus the pytest plugin's capture sink.
    before = len(core.handlers)
    current_id = _accumulator_handler_id(appriser)
    assert type(core.handlers[current_id]._sink) is loguru._simple_sinks.CallableSink

    old_sink_function = core.handlers[current_id]._sink._function
    assert "bound method Appriser.accumulate_log" in str(old_sink_function)

    logger.remove()  # Means: remove all

    assert len(core.handlers) == before
    assert current_id not in core.handlers, f"'{current_id}' should have been removed!"
    new_sink_function = core.handlers[_accumulator_handler_id(appriser)]._sink._function
    assert "bound method Appriser.accumulate_log" in str(new_sink_function)


def test_prevent_removal_of_accumulator_not_removing_it():
    """Test that Appriser doesn't meddle in other handlers"""
    core = logger._core

    before = len(core.handlers)
    accumulator_id = _accumulator_handler_id(appriser)

    mock_id = logger.add(sys.stderr)
    assert len(core.handlers) == before + 1

    assert type(core.handlers[accumulator_id]._sink) is loguru._simple_sinks.CallableSink

    old_sink_function = core.handlers[accumulator_id]._sink._function
    assert "bound method Appriser.accumulate_log" in str(old_sink_function)

    logger.remove(mock_id)  # Only remove the mocked handler

    assert len(core.handlers) == before
    assert accumulator_id in core.handlers  # Nothing should have changed!


def test_every_installed_appriser_survives_logger_remove():
    """logger.remove() used to re-add only the most recently installed Appriser's sink (#8 of the review):
    the module-global appriser then buffered nothing for the rest of the process."""
    second = make_appriser()

    logger.remove()
    logger.error("seen by both")

    assert [m.record["message"] for m in appriser.buffer] == ["seen by both"]
    assert [m.record["message"] for m in second.buffer] == ["seen by both"]
