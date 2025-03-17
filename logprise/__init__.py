from __future__ import annotations

import atexit
import functools
import logging
import sys
import threading
import datetime
from dataclasses import InitVar, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final, Any

import apprise.cli
import loguru
import loguru._logger
from apprise.common import NotifyFormat
from loguru import logger


if TYPE_CHECKING:
    import types
    from collections.abc import Callable, Iterable

    from apprise import AppriseAsset, AppriseConfig, ConfigBase, NotifyBase

__all__ = ["appriser", "logger"]


# Helper function for timestamp
def _timestamp() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


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
    flush_every_x_seconds: InitVar[int | float] = 3600  # Default 1 hour in seconds

    _flush_interval: int | float = field(init=False, default=flush_every_x_seconds)
    _flush_thread: threading.Thread | None = field(init=False, default=None)
    _stop_event: threading.Event = field(init=False, default_factory=threading.Event)

    apprise_obj: apprise.Apprise = field(init=False, default_factory=apprise.Apprise)
    _notification_level: int = field(init=False, default=loguru.logger.level("ERROR").no)
    buffer: list[loguru.Message] = field(init=False, default_factory=list)

    _accumulator_id: ClassVar[int | None] = None
    _old_logger_remove: Final[Callable] = loguru._Logger.remove
    _instance: "Appriser" = field(init=False, default=None)

    def __new__(cls, *args: Any, **kwargs: Any) -> "Appriser":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __post_init__(self, apprise_trigger_level: int | str | loguru.Level, flush_every_x_seconds: int | float) -> None:
        self._load_default_config_paths()
        self.notification_level = apprise_trigger_level or "ERROR"
        self._setup_interception_handler()
        self._setup_exception_hook()
        self.flush_interval = flush_every_x_seconds
        self._setup_at_exit_cleanup()
        self._setup_removal_prevention()

    @property
    def flush_interval(self) -> int | float:
        return self._flush_interval

    @flush_interval.setter
    def flush_interval(self, interval: int | float) -> None:
        self._flush_interval = interval
        self.stop_periodic_flush()
        self._start_periodic_flush()

    def _setup_removal_prevention(self) -> None:
        def _readd():
            print(f"[{_timestamp()}] id: {Appriser._accumulator_id}")
            print(f"[{_timestamp()}] handlers: {logger._core.handlers}")
            if Appriser._accumulator_id not in logger._core.handlers:
                print(f"[{_timestamp()}] --> ADDING!")
                Appriser._accumulator_id = logger.add(self.accumulate_log, catch=False)

        @functools.wraps(self._old_logger_remove)
        def _new_remove(*args: object, **kwargs: object) -> None:
            self._old_logger_remove(*args, **kwargs)
            _readd()

        loguru._Logger.remove = _new_remove
        _readd()

    def _setup_at_exit_cleanup(self) -> None:
        atexit.register(self.cleanup)

    def _load_default_config_paths(self) -> None:
        config = apprise.AppriseConfig()
        for p in apprise.cli.DEFAULT_CONFIG_PATHS:
            if (resolved := Path(p).expanduser().resolve().absolute()).is_file():
                config.add(str(resolved))
        self.apprise_obj.add(config)

    def _setup_interception_handler(self) -> None:
        logging.basicConfig(handlers=[InterceptHandler()], level=self._notification_level, force=True)

    def _setup_exception_hook(self) -> None:
        """Set up a hook to capture uncaught exceptions."""
        original_excepthook = sys.excepthook

        def uncaught_exception(
                exc_type: type[BaseException], exc_value: BaseException, exc_traceback: types.TracebackType | None
        ) -> None:
            # Log the exception
            logger.opt(exception=(exc_type, exc_value, exc_traceback)).error(
                f"Uncaught exception: {exc_type.__name__}: {exc_value}"
            )
            # Force send the notification immediately for uncaught exceptions
            self.send_notification()
            # Call the original excepthook
            original_excepthook(exc_type, exc_value, exc_traceback)

        sys.excepthook = uncaught_exception

    def _periodic_flush(self) -> None:
        """Periodically flush log buffer."""
        while not self._stop_event.is_set():
            # Wait for the specified interval, but allow early termination
            if self._stop_event.wait(self.flush_interval):
                break
            print(f"[{_timestamp()}] ==================================================")
            print(f"[{_timestamp()}] Flushing log buffer ({len(self.buffer)}).")
            for line in self.buffer:
                print(f"[{_timestamp()}]   - {line}")
            print(f"[{_timestamp()}] ==================================================")
            self.send_notification()

    def _start_periodic_flush(self) -> None:
        """Start the periodic flush thread."""
        self._stop_event.clear()
        self._flush_thread = threading.Thread(target=self._periodic_flush, daemon=True, name="logprise-flush")
        self._flush_thread.start()

    def add(
            self,
            servers: str | dict | Iterable | ConfigBase | NotifyBase | AppriseConfig,
            asset: AppriseAsset = None,
            tag: list[str] | None = None,
    ) -> bool:
        """
        Adds one or more server URLs into our list.

        This is a direct wrapper around the `apprise.Apprise.add()` method.
        For detailed documentation, see:
        https://github.com/caronc/apprise/wiki/Development_API#add-add-a-new-notification-service-by-urls

        Returns:
            True if the server(s) were added successfully, False otherwise.
        """

        return self.apprise_obj.add(servers=servers, asset=asset, tag=tag)

    def clear(self) -> None:
        self.apprise_obj.clear()
        self.buffer.clear()
        self._stop_event.clear()

    def stop_periodic_flush(self) -> None:
        """Stop the periodic flush thread."""
        print(f"flush thread: {self._flush_thread}")
        print(f"flush thread alive?: {self._flush_thread and self._flush_thread.is_alive()}")
        if self._flush_thread and self._flush_thread.is_alive():
            self._stop_event.set()
            self._flush_thread.join(timeout=1.0)  # Wait for thread to terminate

    def cleanup(self) -> None:
        """Clean up resources and send any pending notifications."""
        self.stop_periodic_flush()
        self.send_notification()

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
        print(f"[{_timestamp()}] [accumulate_log] {message}")
        if message.record["level"].no >= self.notification_level:
            print(f"[{_timestamp()}] --> ADDING TO BUFFER")
            self.buffer.append(message)
            print(f"[{_timestamp()}] --> BUFFER: {self.buffer}")

    def send_notification(self) -> None:
        """Send a single notification with all accumulated logs."""
        if not self.buffer:
            return

        # Format the buffered logs into a single message
        message = "".join(self.buffer).replace("\r", "")
        if not self.apprise_obj or self.apprise_obj.notify(
                title="Script Notifications", body=message, body_format=NotifyFormat.TEXT
        ):
            print(f"[{_timestamp()}] *** REMOVING BUFFER")
            self.buffer.clear()  # Clear the buffer after sending


appriser = Appriser()