from __future__ import annotations

import atexit
import functools
import inspect
import logging
import sys
import sysconfig
import threading
from functools import partial
from logging import StreamHandler
from pathlib import Path
from threading import get_ident
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
    _exit_via_unhandled_exception: ClassVar[bool] = False

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
        self._setup_sys_exception_hook()
        self._setup_threading_exception_hook()
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

        original_method = logging.Logger._log

        # Check if already intercepted by our method
        if hasattr(original_method, "_intercepted_by_logprise"):
            return

        @functools.wraps(original_method)
        def new_log_method(self: logging.Logger, *args: object, **kwargs: object) -> None:
            if not getattr(self, "_has_been_handled_by_interceptor", False):
                if not any(isinstance(h, InterceptHandler) for h in self.handlers):
                    self.addHandler(InterceptHandler())
                for handler in self.handlers.copy():
                    if isinstance(handler, StreamHandler):
                        self.removeHandler(handler)
                self.propagate = False
                self._added_intercept_handler = True

            return original_method(self, *args, **kwargs)

        # Mark our wrapper with a custom attribute
        new_log_method._intercepted_by_logprise = True
        logging.Logger._log = new_log_method

    def _setup_sys_exception_hook(self) -> None:
        """Set up a hook to capture uncaught exceptions."""
        hook = sys.excepthook

        # We want the original one, not go through multiple Appriser objects!
        while (
            isinstance(hook, partial)
            and hook.func.__name__ == self._handle_uncaught_sys_exception.__name__
            and "original_excepthook" in hook.keywords
        ):
            hook = hook.keywords["original_excepthook"]

        sys.excepthook = partial(self._handle_uncaught_sys_exception, original_excepthook=hook)

    def _setup_threading_exception_hook(self) -> None:
        """Set up a hook to capture uncaught exceptions."""
        hook = threading.excepthook

        # We want the original one, not go through multiple Appriser objects!
        while (
            isinstance(hook, partial)
            and hook.func.__name__ == self._handle_uncaught_threading_exception.__name__
            and "original_excepthook" in hook.keywords
        ):
            hook = hook.keywords["original_excepthook"]

        threading.excepthook = partial(self._handle_uncaught_threading_exception, original_excepthook=hook)

    _STDLIB_BACKPORTS: ClassVar[frozenset[str]] = frozenset(
        {
            "exceptiongroup",  # stdlib in 3.11+
            "importlib_metadata",  # stdlib in 3.8+
            "importlib_resources",  # stdlib in 3.9+
            "typing_extensions",  # backport of typing features
            "tomli",  # tomllib in 3.11+
        }
    )

    @staticmethod
    def _is_method_in_stdlib(method: Callable) -> bool:
        module = inspect.getmodule(method)
        if not module:
            return False

        top_level = method.__module__.split(".", maxsplit=1)[0]

        if top_level in sys.stdlib_module_names or top_level in Appriser._STDLIB_BACKPORTS:
            return True

        if not hasattr(module, "__file__") or not module.__file__:
            return True

        module_path = Path(module.__file__).resolve().absolute()

        if "site-packages" in module_path.parts or "dist-packages" in module_path.parts:
            return False

        all_paths = sysconfig.get_paths()
        for check_this in ["stdlib", "platstdlib"]:
            path = Path(all_paths[check_this]).resolve().absolute()
            if module_path.is_relative_to(path):
                return True

        return False

    def _handle_uncaught_sys_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: types.TracebackType | None,
        original_excepthook: Callable[[type[BaseException], BaseException, types.TracebackType | None], None],
    ) -> None:
        """Handle uncaught exceptions by logging and sending notifications."""
        logger.opt(exception=(exc_type, exc_value, exc_traceback)).error(
            f"Uncaught exception: {exc_type.__name__}: {exc_value}"
        )

        Appriser._exit_via_unhandled_exception = True

        self.send_notification()

        if not self._is_method_in_stdlib(original_excepthook):
            original_excepthook(exc_type, exc_value, exc_traceback)

    def _handle_uncaught_threading_exception(
        self,
        args: threading.ExceptHookArgs,
        /,
        original_excepthook: Callable[[threading.ExceptHookArgs], None],
    ) -> None:
        """Handle uncaught exceptions by logging and sending notifications."""
        logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).error(
            f"Uncaught exception in thread {args.thread.name if args.thread else get_ident()}:"
            f" {args.exc_type.__name__}: {args.exc_value}"
        )

        Appriser._exit_via_unhandled_exception = True

        self.send_notification()

        if not self._is_method_in_stdlib(original_excepthook):
            original_excepthook(args)

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

        if not Appriser._exit_via_unhandled_exception:
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
            logger.debug("No logs to send")
            return

        # Format the buffered logs into a single message
        message = "".join(self.buffer).replace("\r", "")

        try:
            if message and self.apprise_obj.notify(
                title=title, notify_type=notify_type, body=message, body_format=body_format
            ):
                self.buffer.clear()  # Clear the buffer after sending
        except BaseException as e:
            logger.warning(f"Failed to send notification: {e}")


appriser = Appriser()
