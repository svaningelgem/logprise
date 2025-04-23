import logging
import threading
from collections.abc import Callable, Iterable
from typing import ClassVar, Final

import apprise
import loguru
from apprise import NotifyFormat
from loguru import logger

__all__: list[str] = ["appriser", "logger"]

# Type definitions

class InterceptHandler(logging.Handler):
    LOGGING_FILENAMES: ClassVar[set[str]]
    CURRENT_FILENAME: ClassVar[str]

    def _should_ignore_this_frame(self, frame: object) -> bool: ...
    def emit(self, record: logging.LogRecord) -> None: ...

class Appriser:
    apprise_obj: apprise.Apprise
    _notification_level: int
    buffer: list[loguru.Message]
    recursion_depth: int
    flush_interval: int | float

    _flush_thread: threading.Thread | None
    _stop_event: threading.Event

    _accumulator_id: ClassVar[int | None]
    _old_logger_remove: Final[Callable]

    def __init__(
        self,
        apprise_trigger_level: int | str | loguru.Level = "ERROR",
        recursion_depth: int = ...,
        flush_interval: float = 3600,
    ) -> None: ...
    def _load_default_config_paths(self) -> None: ...
    def _setup_interception_handler(self) -> None: ...
    def _setup_exception_hook(self) -> None: ...
    def _periodic_flush(self) -> None: ...
    def _start_periodic_flush(self) -> None: ...
    def _setup_at_exit_cleanup(self) -> None: ...
    def _setup_removal_prevention(self) -> None: ...
    def add(
        self,
        servers: str | dict | Iterable | apprise.ConfigBase | apprise.NotifyBase | apprise.AppriseConfig,
        asset: apprise.AppriseAsset | None = None,
        tag: list[str] | None = None,
    ) -> bool: ...
    def stop_periodic_flush(self) -> None: ...
    def cleanup(self) -> None: ...
    @property
    def notification_level(self) -> int: ...
    @notification_level.setter
    def notification_level(self, value: int | str | loguru.Level) -> None: ...
    def accumulate_log(self, message: loguru.Message) -> None: ...
    def send_notification(
        self, title: str = "Script Notifications", body_format: str | NotifyFormat = ...
    ) -> None: ...

appriser: Appriser
