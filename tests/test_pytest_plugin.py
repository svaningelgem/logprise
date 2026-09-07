"""Direct unit tests for the logprise pytest plugin internals.

The caplog behaviour is covered end to end in test_caplog_integration.py;
this pins the propagation rule the session sink relies on.
"""

from __future__ import annotations

import logging

from logprise import pytest_plugin


def test_reaches_root_follows_the_propagation_chain():
    """A logger propagates to root unless it, or an ancestor, has propagate=False."""
    parent = logging.getLogger("test.reaches")
    child = logging.getLogger("test.reaches.child")
    try:
        assert pytest_plugin._reaches_root("root")
        assert pytest_plugin._reaches_root("test.reaches.child")

        parent.propagate = False
        assert not pytest_plugin._reaches_root("test.reaches.child")
    finally:
        parent.propagate = True
        child.propagate = True
