from __future__ import annotations

import atexit
import functools
import html
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

from logprise._sinks import patch_logger_remove, protect


if TYPE_CHECKING:
    import types
    from collections.abc import Callable
    from typing import Any

    from apprise import AppriseAsset, AppriseConfig, ConfigBase, NotifyBase

    # What apprise.Apprise.add accepts, one at a time or as a list. dict values are apprise's own Any.
    _ServerSpec = str | dict[str, Any] | NotifyBase | AppriseConfig | ConfigBase

__all__ = ["appriser", "logger"]


# Sentinel for a send_notification argument that was not supplied. None is itself a
# meaningful value for body_format (it selects the preformatted-HTML default), so a
# distinct type is needed to tell "omitted" apart from "explicitly None" -- and a named
# type (rather than object()) lets it join the parameter annotations so mypy/stubtest pass.
class _UnsetType: ...


_UNSET: Final = _UnsetType()

# Attribute names used as markers on objects we do not own (loggers, the patched _log).
_INTERCEPTED_FLAG: Final = "_has_been_handled_by_interceptor"
_INTERCEPT_MARK: Final = "_intercepted_by_logprise"


def _is_console_handler(handler: logging.Handler) -> bool:
    """A StreamHandler writing to the process console: exactly what loguru's own stderr sink replaces.

    File handlers (StreamHandler subclasses over a file) and capture handlers over in-memory streams,
    such as pytest's, are the host's business and stay.
    """
    stream = getattr(handler, "stream", None)
    return (
        isinstance(handler, StreamHandler)
        and stream is not None
        and stream in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__)
    )


def _strip_console_handlers(start: logging.Logger) -> None:
    """Remove console handlers from ``start`` and every ancestor up to the root logger."""
    current: logging.Logger | None = start
    while current is not None:
        for handler in current.handlers.copy():
            if _is_console_handler(handler):
                current.removeHandler(handler)
        current = current.parent


def _ensure_intercepted(target: logging.Logger) -> None:
    """Attach an InterceptHandler to ``target`` unless it already has one."""
    if not any(isinstance(h, InterceptHandler) for h in target.handlers):
        target.addHandler(InterceptHandler())


# Intercept standard logging calls and forward them to loguru
class InterceptHandler(logging.Handler):
    LOGGING_FILENAMES: ClassVar[set[str]] = {
        Path(logging.__file__).parent.resolve().absolute().as_posix().lower(),
        # Path(apprise.__file__).parent.resolve().absolute().as_posix().lower(),
        # Path(loguru.__file__).parent.resolve().absolute().as_posix().lower(),
    }
    CURRENT_FILENAME: ClassVar[str] = Path(__file__).resolve().absolute().as_posix().lower()

    def _should_ignore_this_frame(self, frame: types.FrameType) -> bool:
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

        # logging promises never to raise out of a logging call: every stdlib handler routes a failure
        # in its own emit() to handleError(). Keep that promise here too, otherwise a bad %-format in any
        # library unwinds through the host's logging.error(...) call instead of printing a logging error.
        try:
            self._forward(record)
        except Exception:
            self.handleError(record)

    def _forward(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists
        level: int | str
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find the frame that made the logging call. Start from this very frame and count every
        # frame skipped: loguru's depth=N means "N frames above the caller of log()", and that
        # caller is this method. logging.currentframe() is unsuitable as a start: it returns the
        # frame 3 levels up on Python <= 3.10 but 1 level up on 3.11+, so a fixed offset is wrong
        # on one of them and overshoots shallow stacks ("call stack is not deep enough").
        frame, depth = inspect.currentframe(), 0
        while frame is not None and self._should_ignore_this_frame(frame):
            frame = frame.f_back
            depth += 1
        if frame is None:
            depth = 0  # walked off the top (e.g. python -c): attribute to this handler rather than raise

        # Carry the originating stdlib logger name: sinks (the pytest plugin, user sinks) can then tell a
        # forwarded record from a native loguru call and keep the name the host's filters key on.
        logger_opt = logger.bind(_stdlib_logger=record.name).opt(depth=depth, exception=record.exc_info)
        logger_opt.log(level, record.getMessage())


# Custom Appriser class to manage notifications
class Appriser:
    """A wrapper around Apprise to accumulate logs and send notifications."""

    _original_excepthook: Callable[[type[BaseException], BaseException, types.TracebackType | None], None] | None = None
    _original_threading_excepthook: Callable[[threading.ExceptHookArgs], object] | None = None

    def __init__(
        self,
        *,
        apprise_trigger_level: int | str | loguru.Level = "ERROR",
        recursion_depth: int = apprise.cli.DEFAULT_RECURSION_DEPTH,
        flush_interval: float = 3600,
        notify_type: str | NotifyType = NotifyType.WARNING,
        body_format: str | NotifyFormat | None = NotifyFormat.TEXT,
    ) -> None:
        self._installed: bool = False
        self._flush_thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()

        # Internal variables
        self._notification_level: int = loguru.logger.level("ERROR").no  # The default
        self.notification_level = apprise_trigger_level  # Let the property handle the conversion

        self._flush_interval: int | float = 3600  # The default
        self.flush_interval = flush_interval  # Let the property handle the conversion

        # Notification rendering defaults, used by every send_notification (including the
        # automatic flush/cleanup/exception paths). Reassign these to change how the
        # accumulated logs are delivered, e.g. ``appriser.body_format = NotifyFormat.TEXT``
        # for plain-text channels (see send_notification for what body_format=None means).
        self.notify_type: str | NotifyType = notify_type
        self.body_format: str | NotifyFormat | None = body_format

        self.recursion_depth: int = recursion_depth
        self.apprise_obj: apprise.Apprise = apprise.Apprise()
        self.buffer: list[loguru.Message] = []

    def install(self) -> None:
        """Arm every process-global side effect of this Appriser.

        Constructing an :class:`Appriser` only sets up instance-local state.
        This method installs the logging interception, the sys/threading
        exception hooks, the loguru removal prevention, the atexit cleanup, and
        starts the periodic flush thread. It is idempotent: calling it more than
        once is a no-op.
        """
        if self._installed:
            return
        self._installed = True

        self._load_default_config_paths()
        self._setup_interception_handler()
        self._setup_sys_exception_hook()
        self._setup_threading_exception_hook()
        self._start_periodic_flush()
        self._setup_at_exit_cleanup()
        self._setup_removal_prevention()

    def _setup_removal_prevention(self) -> None:
        patch_logger_remove()
        protect(self.accumulate_log)

    def _setup_at_exit_cleanup(self) -> None:
        atexit.register(self.cleanup)

    def _load_default_config_paths(self) -> None:
        config = apprise.AppriseConfig()
        for p in apprise.cli.DEFAULT_CONFIG_PATHS:
            if (resolved := Path(p).expanduser().resolve().absolute()).is_file():
                config.add(str(resolved))
        self.apprise_obj.add(config)

    def _setup_interception_handler(self) -> None:
        # The root logger keeps everything the host gave it: its level (the apprise trigger level is a
        # notification threshold, not a log level; passing it as basicConfig(level=...) once dropped every
        # record below ERROR, #170) and its non-console handlers. basicConfig(force=True) would close and
        # remove a host FileHandler; only console handlers go, since loguru's own stderr sink replaces them.
        root = logging.getLogger()
        _strip_console_handlers(root)
        _ensure_intercepted(root)

        # Typed loosely on purpose: the wrapper forwards whatever signature this Python's _log has.
        original_method: Callable[..., None] = logging.Logger._log

        # Check if already intercepted by our method
        if hasattr(original_method, _INTERCEPT_MARK):
            return

        @functools.wraps(original_method)
        def new_log_method(self: logging.Logger, *args: object, **kwargs: object) -> None:
            # Every call: logging.config.dictConfig/fileConfig replace a logger's handlers wholesale, so a
            # handler attached only once would be gone for good. Re-attaching is cheap and keeps the
            # logger intercepted however often the host reconfigures logging.
            _ensure_intercepted(self)

            # Once per logger: console handlers on it and its ancestors would print every record a second
            # time next to loguru's output, so they go. Everything else (file handlers, capture handlers,
            # propagation) is the host's and stays, and doing this once means later host changes stick.
            if not getattr(self, _INTERCEPTED_FLAG, False):
                setattr(self, _INTERCEPTED_FLAG, True)
                _strip_console_handlers(self)

            return original_method(self, *args, **kwargs)

        # Mark our wrapper with a custom attribute
        setattr(new_log_method, _INTERCEPT_MARK, True)
        logging.Logger._log = new_log_method  # type: ignore[method-assign]

    def _setup_sys_exception_hook(self) -> None:
        """Set up a hook to capture uncaught exceptions."""
        self._original_excepthook = hook = sys.excepthook

        # We want the original one, not go through multiple Appriser objects!
        while (
            isinstance(hook, partial)
            and hook.func.__name__ == self._handle_uncaught_sys_exception.__name__
            and isinstance(hook.keywords, dict)
            and "original_excepthook" in hook.keywords
        ):
            hook = hook.keywords["original_excepthook"]

        sys.excepthook = partial(self._handle_uncaught_sys_exception, original_excepthook=hook)

    def _setup_threading_exception_hook(self) -> None:
        """Set up a hook to capture uncaught exceptions."""
        self._original_threading_excepthook = hook = threading.excepthook

        # We want the original one, not go through multiple Appriser objects!
        while (
            isinstance(hook, partial)
            and hook.func.__name__ == self._handle_uncaught_threading_exception.__name__
            and isinstance(hook.keywords, dict)
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
    def _is_method_in_stdlib(method: Callable[..., object]) -> bool:
        # A functools.partial has no module of its own: attribute lookup falls through to its type and
        # answers "functools", which would make any host hook bound with partial look like the stdlib one.
        while isinstance(method, partial):
            method = method.func
        module = inspect.getmodule(method)
        if not module:
            return False

        top_level = (getattr(method, "__module__", None) or "").split(".", maxsplit=1)[0]

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

        self.send_notification()

        if not self._is_method_in_stdlib(original_excepthook):
            original_excepthook(exc_type, exc_value, exc_traceback)

    def _handle_uncaught_threading_exception(
        self,
        args: threading.ExceptHookArgs,
        /,
        original_excepthook: Callable[[threading.ExceptHookArgs], object],
    ) -> None:
        """Handle uncaught exceptions by logging and sending notifications."""
        # threading.excepthook silently ignores SystemExit: ending a thread with sys.exit() is not an error.
        if args.exc_type is not SystemExit:
            logger.opt(exception=(args.exc_type, args.exc_value, args.exc_traceback)).error(
                f"Uncaught exception in thread {args.thread.name if args.thread else get_ident()}:"
                f" {args.exc_type.__name__}: {args.exc_value}"
            )

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
            if self._installed:
                self.stop_periodic_flush()
                self._start_periodic_flush()

    def _periodic_flush(self, stop_event: threading.Event | None = None) -> None:
        """Periodically flush the log buffer until ``stop_event`` (this thread's own) is set."""
        stop_event = stop_event or self._stop_event
        while not stop_event.is_set():
            # Wait for the specified interval but allow early termination
            if stop_event.wait(self._flush_interval):
                break

            self.send_notification()

    def _start_periodic_flush(self) -> None:
        """Start the periodic flush thread."""
        # Every thread gets its own stop event. Reusing one and clearing it here revived a previous
        # thread that had been told to stop but was still inside a slow send when the join timed out,
        # leaving two threads flushing the same buffer.
        self._stop_event = threading.Event()
        self._flush_thread = threading.Thread(
            target=self._periodic_flush, args=(self._stop_event,), daemon=True, name="logprise-flush"
        )
        self._flush_thread.start()

    def add(
        self,
        servers: _ServerSpec | list[_ServerSpec],
        asset: AppriseAsset | None = None,
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
        """Discard any buffered logs that have not been sent yet."""
        self.buffer.clear()

    def stop_periodic_flush(self) -> None:
        """Stop the periodic flush thread."""
        if self._flush_thread and self._flush_thread.is_alive():
            self._stop_event.set()
            self._flush_thread.join(timeout=1.0)  # Wait for thread to terminate

    def cleanup(self) -> None:
        """Clean up resources and send any pending notifications."""
        if not self._installed:
            return  # nothing was armed, so there is nothing to flush and no hooks of ours to restore

        self.stop_periodic_flush()

        # Always flush: a batch the exception hooks already delivered leaves an empty buffer (a no-op
        # here), and one they could not deliver gets its retry.
        self.send_notification()

        sys.excepthook = self._original_excepthook or sys.__excepthook__
        threading.excepthook = self._original_threading_excepthook or threading.__excepthook__

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
        notify_type: str | NotifyType | _UnsetType = _UNSET,
        body_format: str | NotifyFormat | _UnsetType | None = _UNSET,
    ) -> None:
        """
        Send a single notification with all accumulated logs.

        ``notify_type`` and ``body_format`` fall back to the instance attributes (set in
        ``__init__`` or reassigned directly) when omitted, so the automatic flush,
        cleanup, and exception paths honour them too. ``None`` is a meaningful value for
        ``body_format`` (it selects the preformatted-HTML default below), so the sentinel
        ``_UNSET`` — not ``None`` — marks "argument not supplied".

        With ``body_format=None`` the logs are delivered as a preformatted HTML ``<pre>``
        block so whitespace survives verbatim. Pass an explicit format
        (e.g. ``NotifyFormat.TEXT`` / ``MARKDOWN`` / ``HTML``) to override.
        """
        if isinstance(notify_type, _UnsetType):
            notify_type = self.notify_type
        if isinstance(body_format, _UnsetType):
            body_format = self.body_format

        if not self.buffer:
            logger.trace("No logs to send")
            return

        # Detach the batch before delivering. Records that arrive while a send is in flight (the flush
        # thread runs concurrently with the host, and a target's own error logging is intercepted
        # straight back here) then land in the fresh buffer instead of being wiped after the send.
        batch, self.buffer = self.buffer, []

        if not len(self.apprise_obj):
            # No services configured: skip notifying so apprise doesn't log
            # "There are no service(s) to notify" for every flush. Drop the
            # detached batch too -- services should have been configured by now,
            # and there is nowhere to deliver them, so keeping them only leaks memory.
            logger.trace("No notification services configured; discarding buffered logs")
            return

        # Format the buffered logs into a single message
        message = "".join(batch).replace("\r", "")

        # Default path: deliver the logs as a preformatted HTML block. apprise's TEXT->HTML
        # conversion escapes every space to &nbsp; (apprise.URLBase.escape_html), which mangles
        # copy-pasted shell commands and indented tracebacks in the HTML alternative most mail
        # clients display. A <pre> block preserves whitespace verbatim and stops Markdown from
        # interpreting traceback tokens (e.g. __init__, *args). An explicit body_format opts out.
        body, resolved_format = message, body_format
        if resolved_format is None:
            body, resolved_format = f"<pre>{html.escape(message)}</pre>", NotifyFormat.HTML

        # Deliver to each target separately. Apprise.notify() collapses every target into a single
        # bool, so one unreachable target would keep the buffer forever and re-send the whole backlog
        # to the healthy targets on every flush (#167). The batch is done as soon as any target took
        # it; a batch nobody could deliver goes back for the next attempt.
        delivered = False
        for server in self.apprise_obj:
            try:
                delivered = (
                    apprise.Apprise(servers=server).notify(
                        title=title, notify_type=notify_type, body=body, body_format=resolved_format
                    )
                    or delivered
                )
            except BaseException as e:
                logger.warning(f"Failed to send notification: {e}")
        if not delivered:
            self.buffer[:0] = batch  # ahead of whatever accumulated meanwhile


appriser = Appriser()
appriser.install()
