"""Direct unit tests for the logprise pytest plugin internals.

The caplog-integration behaviour is covered in test_caplog_integration.py;
this exercises the sink helper in isolation to reach the branch the
fixture-driven path does not.
"""

from __future__ import annotations

from logprise import pytest_plugin


def test_sink_returns_early_when_no_fixture():
    """The sink is a no-op (and never touches message.record) without a fixture."""
    pytest_plugin._state.fixture = None
    assert pytest_plugin._loguru_to_caplog("ignored message") is None
