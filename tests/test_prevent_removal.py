import sys

import loguru
import loguru._simple_sinks

from logprise import logger


def _accumulator_handler_ids() -> list[int]:
    """Ids of every loguru handler whose sink is an ``Appriser.accumulate_log`` bound method."""
    return [
        handler_id
        for handler_id, handler in logger._core.handlers.items()
        if type(handler._sink) is loguru._simple_sinks.CallableSink
        and "bound method Appriser.accumulate_log" in str(handler._sink._function)
    ]


def test_prevent_removal_of_accumulator():
    """Test that Appriser keeps adding its interception"""
    core = logger._core

    # The silence autofixture removed everything else; whatever is left is what logprise keeps alive.
    before = len(core.handlers)
    old_ids = _accumulator_handler_ids()
    assert len(old_ids) == 1  # exactly one accumulator, before ...

    logger.remove()  # Means: remove all

    assert len(core.handlers) == before
    new_ids = _accumulator_handler_ids()
    assert len(new_ids) == 1  # ... and exactly one after
    assert old_ids != new_ids, "the accumulator must have been re-added under a new id"


def test_prevent_removal_of_accumulator_not_removing_it():
    """Test that Appriser doesn't meddle in other handlers"""
    core = logger._core

    before = len(core.handlers)
    accumulator_ids = _accumulator_handler_ids()
    assert len(accumulator_ids) == 1

    mock_id = logger.add(sys.stderr)
    assert len(core.handlers) == before + 1

    logger.remove(mock_id)  # Only remove the mocked handler

    assert len(core.handlers) == before
    assert _accumulator_handler_ids() == accumulator_ids  # Nothing should have changed!
