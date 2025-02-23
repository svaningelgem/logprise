from __future__ import annotations

import atexit
import logging
from dataclasses import field, dataclass, InitVar
from pathlib import Path
from typing import ClassVar

import apprise.cli
import loguru._logger
from loguru import logger

__all__ = ["logger", "appriser"]


# Intercept standard logging calls and forward them to loguru
class InterceptHandler(logging.Handler):
    LOGGING_FILENAMES: ClassVar[set[str]] = {
        Path(logging.__file__).parent.resolve().absolute().as_posix().lower(),
        # Path(apprise.__file__).parent.resolve().absolute().as_posix().lower(),
        # Path(loguru.__file__).parent.resolve().absolute().as_posix().lower(),
    }
    CURRENT_FILENAME: ClassVar[str] = Path(__file__).resolve().absolute().as_posix().lower()

    def _should_ignore_this_frame(self, frame: object) -> bool:
        filename = Path(frame.f_code.co_filename).resolve().absolute().as_posix().lower()
        if filename == self.CURRENT_FILENAME:
            return True
        if "jetbrains/intellij" in filename:
            return True
        if filename == "<string>":
            return True

        return any(skip_path in filename for skip_path in self.LOGGING_FILENAMES)

    def emit(self, record: logging.LogRecord) -> None:
        # Skip if this is a propagated record we've already handled
        if hasattr(record, "_has_been_handled_by_interceptor"):
            return

        # Mark record as handled to prevent duplicate processing
        record._has_been_handled_by_interceptor = True

        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 0
        while self._should_ignore_this_frame(frame):
            frame = frame.f_back
            depth += 1

        # Get the actual logger name instead of 'logging'
        logger_opt = logger.opt(depth=depth + 2, exception=record.exc_info)
        logger_opt.log(level, record.getMessage())


# Custom Appriser class to manage notifications
@dataclass
class Appriser:
    """A wrapper around Apprise to accumulate logs and send notifications."""

    apprise_trigger_level: InitVar[int | str | loguru.Level] = "ERROR"

    recursion_depth: int = apprise.cli.DEFAULT_RECURSION_DEPTH

    apprise_obj: apprise.Apprise = field(init=False, default_factory=apprise.Apprise)
    _notification_level: int = field(init=False, default=logger.level("ERROR").no)
    buffer: list[loguru.Record] = field(init=False, default_factory=list)

    def _load_default_config_paths(self) -> None:
        config = apprise.AppriseConfig()
        for p in apprise.cli.DEFAULT_CONFIG_PATHS:
            if (resolved := Path(p).expanduser().resolve().absolute()).is_file():
                config.add(str(resolved))
        self.apprise_obj.add(config)

    def _setup_interception_handler(self) -> None:
        logging.basicConfig(handlers=[InterceptHandler()], level=self._notification_level, force=True)

    def __post_init__(self, apprise_trigger_level: int | str | loguru.Level) -> None:
        self._load_default_config_paths()
        self.notification_level = apprise_trigger_level or "ERROR"
        logger.add(self.accumulate_log, catch=False)
        self._setup_interception_handler()

    @property
    def notification_level(self) -> int:
        return self._notification_level

    @notification_level.setter
    def notification_level(self, value: int | str | loguru.Level) -> None:
        """Set the minimum log level for triggering notifications."""
        if isinstance(value, int):
            self._notification_level = value
        elif isinstance(value, str):
            self._notification_level = logger.level(value).no
        elif isinstance(value, loguru._logger.Level):
            self._notification_level = value.no
        else:
            raise TypeError(f"'{value}' is {type(value)}, expecting int/str/Level")

    def accumulate_log(self, message: loguru.Message) -> None:
        """Accumulate logs that meet or exceed the notification level."""
        record = message.record
        if record["level"].no >= self.notification_level:
            self.buffer.append(record)

    def send_notification(self) -> None:
        """Send a single notification with all accumulated logs."""
        if not self.buffer:
            return

        # Format the buffered logs into a single message
        message = "\n".join(f"{record['level'].name}: {record['message']}" for record in self.buffer)
        self.apprise_obj.notify(title="Script Notifications", body=message)
        self.buffer.clear()  # Clear the buffer after sending


appriser = Appriser()
atexit.register(appriser.send_notification)
