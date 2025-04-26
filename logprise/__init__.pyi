import logging
from collections.abc import Iterable
from typing import ClassVar

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
    buffer: list[loguru.Message]
    recursion_depth: int = ...
    flush_interval: int | float = 3600
    apprise_trigger_level: ClassVar[str] = "ERROR"

    def __init__(
        self,
        *,
        apprise_trigger_level: int | str | loguru.Level = "ERROR",
        recursion_depth: int = ...,
        flush_interval: float = 3600,
    ) -> None: ...
    def add(
        self,
        servers: str
        | dict[str, object]
        | Iterable[str]
        | apprise.ConfigBase
        | apprise.NotifyBase
        | apprise.AppriseConfig,
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
        self,
        title: str = "Script Notifications",
        notify_type: str | apprise.NotifyType = ...,
        body_format: str | NotifyFormat = ...,
    ) -> None: ...

appriser: Appriser
