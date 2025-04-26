from __future__ import annotations

import atexit
import functools
import logging
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final

import apprise.cli
import loguru
import loguru._logger
from apprise import NotifyType
from apprise.common import NotifyFormat
from loguru import logger


if TYPE_CHECKING:
    import types
    from collections.abc import Callable, Iterable

    from apprise import AppriseAsset, AppriseConfig, ConfigBase, NotifyBase

__all__ = ["appriser", "logger"]


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
        if filename.endswith("<string>"):
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


_old_logger_remove: Final[Callable[[loguru.Logger, int | None], None]] = loguru._Logger.remove


# Custom Appriser class to manage notifications
class Appriser:
    """A wrapper around Apprise to accumulate logs and send notifications."""

    _accumulator_id: ClassVar[int | None] = None

    def __init__(
        self,
        *,
        apprise_trigger_level: int | str | loguru.Level = "ERROR",
        recursion_depth: int = apprise.cli.DEFAULT_RECURSION_DEPTH,
        flush_interval: float = 3600,
    ) -> None:
        self._flush_thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()

        # Internal variables
        self._notification_level: int = loguru.logger.level("ERROR").no  # The default
        self.notification_level = apprise_trigger_level or "ERROR"  # Let the property handle the conversion

        self._flush_interval: int | float = 3600  # The default
        self.flush_interval = flush_interval  # Let the property handle the conversion

        self.recursion_depth: int = recursion_depth
        self.apprise_obj: apprise.Apprise = apprise.Apprise()
        self.buffer: list[loguru.Message] = []

        # Initialize everything
        self._load_default_config_paths()
        self._setup_interception_handler()
        self._setup_exception_hook()
        self._start_periodic_flush()
        self._setup_at_exit_cleanup()
        self._setup_removal_prevention()

    def _setup_removal_prevention(self) -> None:
        @functools.wraps(_old_logger_remove)
        def _new_remove(*args: object, **kwargs: object) -> None:
            _old_logger_remove(*args, **kwargs)

            if Appriser._accumulator_id not in logger._core.handlers:
                Appriser._accumulator_id = logger.add(self.accumulate_log, catch=False)

        loguru._Logger.remove = _new_remove
        Appriser._accumulator_id = logger.add(self.accumulate_log, catch=False)

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

    @property
    def flush_interval(self) -> int | float:
        return self._flush_interval

    @flush_interval.setter
    def flush_interval(self, value: float) -> None:
        """Set the flush interval."""
        if not isinstance(value, int | float) or value <= 0:
            raise ValueError(f"Flush interval must be a positive number, got {value}")

        if self._flush_interval != value:
            self._flush_interval = value
            self.stop_periodic_flush()
            self._start_periodic_flush()

    def _periodic_flush(self) -> None:
        """Periodically flush log buffer."""
        while not self._stop_event.is_set():
            # Wait for the specified interval but allow early termination
            if self._stop_event.wait(self._flush_interval):
                break

            self.send_notification()

    def _start_periodic_flush(self) -> None:
        """Start the periodic flush thread."""
        self._stop_event.clear()
        self._flush_thread = threading.Thread(target=self._periodic_flush, daemon=True, name="logprise-flush")
        self._flush_thread.start()

    def add(
        self,
        servers: str | dict[str, object] | Iterable[str] | ConfigBase | NotifyBase | AppriseConfig,
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

    def stop_periodic_flush(self) -> None:
        """Stop the periodic flush thread."""
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
        if message.record["level"].no >= self.notification_level:
            self.buffer.append(message)

    def send_notification(
        self,
        title: str = "Script Notifications",
        notify_type: str | NotifyType = NotifyType.WARNING,
        body_format: str | NotifyFormat = NotifyFormat.TEXT,
    ) -> None:
        """Send a single notification with all accumulated logs."""
        if not self.buffer:
            return

        # Format the buffered logs into a single message
        message = "".join(self.buffer).replace("\r", "")

        if self.apprise_obj and self.apprise_obj.notify(
            title=title, notify_type=notify_type, body=message, body_format=body_format
        ):
            self.buffer.clear()  # Clear the buffer after sending


appriser = Appriser()
