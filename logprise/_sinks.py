"""Loguru sinks that survive ``logger.remove()``.

logprise needs a few sinks to stay alive whatever the host does to loguru:
every installed Appriser's accumulator (otherwise notifications silently
stop) and, under pytest, the plugin's capture sink. ``logger.remove()`` is
wrapped once; after the real remove it re-adds any protected sink the call
took out.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Final

from loguru import logger


if TYPE_CHECKING:
    from collections.abc import Callable

    import loguru

_original_remove: Final[Callable[[loguru.Logger, int | None], None]] = type(logger).remove

# sink -> (current handler id, the level it was added with)
protected: dict[Callable[[loguru.Message], None], tuple[int, int | str]] = {}


def protect(sink: Callable[[loguru.Message], None], *, level: int | str = "DEBUG") -> None:
    """Add ``sink`` to loguru and keep it there across ``logger.remove()``."""
    protected[sink] = (logger.add(sink, catch=False, level=level), level)


def unprotect(sink: Callable[[loguru.Message], None]) -> None:
    """Remove a protected sink for good; a no-op for a sink that is not (or no longer) protected."""
    entry = protected.pop(sink, None)
    if entry is not None:
        _original_remove(logger, entry[0])


@functools.wraps(_original_remove)
def _remove_keeping_protected(self: loguru.Logger, handler_id: int | None = None) -> None:
    _original_remove(self, handler_id)
    for sink, (current_id, level) in protected.items():
        if handler_id is None or handler_id == current_id:
            protected[sink] = (logger.add(sink, catch=False, level=level), level)


def patch_logger_remove() -> None:
    """Install the wrapper on loguru's Logger class; safe to call more than once."""
    type(logger).remove = _remove_keeping_protected  # type: ignore[method-assign]
