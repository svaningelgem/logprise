import logging
import re
from logging import NullHandler, StreamHandler

import pytest
from apprise import NotifyFormat, NotifyType
from conftest import make_appriser
from loguru import logger

from logprise import InterceptHandler


def test_intercept_handler_forwards_to_loguru():
    """Test that standard logging messages get forwarded to loguru"""
    # Configure standard logging to use our handler
    standard_logger = logging.getLogger("test_logger")
    standard_logger.setLevel(logging.DEBUG)

    # Create an Appriser to capture the logs
    appriser = make_appriser()

    # Log using standard logging
    test_message = "Test log message"
    standard_logger.error(test_message)

    # Verify the message was captured by our appriser
    assert len(appriser.buffer) == 1
    assert appriser.buffer[0].record["message"] == test_message
    assert appriser.buffer[0].record["level"].name == "ERROR"


def test_appriser_notification_levels():
    """Test that Appriser respects different notification levels"""
    appriser = make_appriser(apprise_trigger_level="WARNING")

    # These should be captured
    logger.warning("Test warning")
    logger.error("Test error")
    logger.critical("Test critical")

    # These should not be captured
    logger.debug("Test debug")
    logger.info("Test info")

    assert len(appriser.buffer) == 3
    assert all(message.record["level"].no >= logger.level("WARNING").no for message in appriser.buffer)


def test_send_notification(apprise_noop):
    """Test the complete flow from logging to notification"""
    appriser, noop = apprise_noop

    # Generate some logs
    logger.error("Database connection failed")
    logger.critical("System shutdown initiated")

    # Send notification
    appriser.send_notification()

    # Verify notification content
    assert len(noop.calls) == 1
    notification = noop.calls[0]
    assert notification["title"] == "Script Notifications"
    assert re.search(
        r" \| ERROR    \| test_logprise:test_send_notification:\d+ - Database connection failed", notification["body"]
    )
    assert re.search(
        r" \| CRITICAL \| test_logprise:test_send_notification:\d+ - System shutdown initiated", notification["body"]
    )

    # Buffer should be cleared after sending
    assert len(appriser.buffer) == 0


def test_html_opt_in_sends_preformatted_block_preserving_whitespace(mocker, apprise_noop):
    """body_format=None opts into an HTML <pre> block so whitespace survives apprise's space->&nbsp; HTML escaping."""
    appriser, _noop = apprise_noop
    appriser.body_format = None  # opt into the preformatted-HTML path
    appriser.buffer.append("run:  pkill -f my_worker.py")  # double space + command spaces must survive intact
    mock_notify = mocker.patch.object(appriser.apprise_obj, "notify")

    appriser.send_notification()

    mock_notify.assert_called_once()
    kwargs = mock_notify.call_args.kwargs
    assert kwargs["body_format"] == NotifyFormat.HTML
    assert kwargs["body"] == "<pre>run:  pkill -f my_worker.py</pre>"
    assert "&nbsp;" not in kwargs["body"]
    assert len(appriser.buffer) == 0


def test_html_opt_in_escapes_markup_but_leaves_spaces_and_underscores(mocker, apprise_noop):
    """<pre> escapes HTML metacharacters but leaves indentation/underscores intact (no Markdown mangling)."""
    appriser, _noop = apprise_noop
    appriser.body_format = None  # opt into the preformatted-HTML path
    appriser.buffer.append("    obj.__init__() & <x>")  # 4-space indent, dunder, &, angle brackets
    mock_notify = mocker.patch.object(appriser.apprise_obj, "notify")

    appriser.send_notification()

    assert mock_notify.call_args.kwargs["body"] == "<pre>    obj.__init__() &amp; &lt;x&gt;</pre>"


def test_explicit_body_format_is_not_wrapped(mocker, apprise_noop):
    """An explicit body_format is honored as-is — the <pre> wrapping is only the None default."""
    appriser, _noop = apprise_noop
    appriser.buffer.append("plain text")
    mock_notify = mocker.patch.object(appriser.apprise_obj, "notify")

    appriser.send_notification(body_format=NotifyFormat.TEXT)

    kwargs = mock_notify.call_args.kwargs
    assert kwargs["body"] == "plain text"
    assert kwargs["body_format"] == NotifyFormat.TEXT


def test_instance_body_format_attribute_is_used_when_arg_omitted(mocker, apprise_noop):
    """The instance body_format drives the auto-flush path (send_notification with no args)."""
    appriser, _noop = apprise_noop
    appriser.body_format = NotifyFormat.TEXT  # reconfigure the default rendering
    appriser.buffer.append("plain text")
    mock_notify = mocker.patch.object(appriser.apprise_obj, "notify")

    appriser.send_notification()  # omit body_format -> falls back to the instance attribute

    kwargs = mock_notify.call_args.kwargs
    assert kwargs["body"] == "plain text"  # not wrapped in <pre>
    assert kwargs["body_format"] == NotifyFormat.TEXT


def test_explicit_none_forces_html_over_instance_attribute(mocker, apprise_noop):
    """body_format=None is distinct from omitted: it forces the <pre>-HTML default."""
    appriser, _noop = apprise_noop
    appriser.body_format = NotifyFormat.TEXT  # instance default is plain text...
    appriser.buffer.append("run:  pkill -f x")
    mock_notify = mocker.patch.object(appriser.apprise_obj, "notify")

    appriser.send_notification(body_format=None)  # ...but None overrides it for this call

    kwargs = mock_notify.call_args.kwargs
    assert kwargs["body"] == "<pre>run:  pkill -f x</pre>"
    assert kwargs["body_format"] == NotifyFormat.HTML


def test_instance_notify_type_attribute_is_used_when_arg_omitted(mocker, apprise_noop):
    """The instance notify_type drives the auto-flush path too."""
    appriser, _noop = apprise_noop
    appriser.notify_type = NotifyType.FAILURE
    appriser.buffer.append("boom")
    mock_notify = mocker.patch.object(appriser.apprise_obj, "notify")

    appriser.send_notification()

    assert mock_notify.call_args.kwargs["notify_type"] == NotifyType.FAILURE


def test_send_notification_empty():
    """Test sending notification with no triggers"""
    appriser = make_appriser(apprise_trigger_level="ERROR")

    # Log messages below notification level
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")

    # Nothing should be in buffer
    assert len(appriser.buffer) == 0

    # Send notification (should do nothing)
    appriser.send_notification()
    assert len(appriser.buffer) == 0


def test_send_notification_discards_buffer_when_no_services(mocker):
    """With logs buffered but no services configured, notify is skipped and the buffer dropped.

    Skipping the call avoids apprise logging 'There are no service(s) to notify' on every
    flush; dropping the buffer avoids accumulating undeliverable logs forever.
    """
    appriser = make_appriser(apprise_trigger_level="ERROR")
    assert len(appriser.apprise_obj) == 0  # no services configured

    logger.error("Boom")
    assert len(appriser.buffer) == 1

    mock_notify = mocker.patch.object(appriser.apprise_obj, "notify")
    appriser.send_notification()

    mock_notify.assert_not_called()
    # Nothing can deliver the logs, so they are discarded rather than hoarded.
    assert len(appriser.buffer) == 0


def test_clear_discards_buffer_but_keeps_services(apprise_noop):
    """clear() drops buffered logs while leaving configured services intact."""
    appriser, _ = apprise_noop

    logger.error("Boom")
    assert len(appriser.buffer) == 1
    assert len(appriser.apprise_obj) == 1

    appriser.clear()

    assert len(appriser.buffer) == 0
    assert len(appriser.apprise_obj) == 1  # services are preserved


def test_send_notification_buffer_kept_when_notify_reports_failure(mocker, apprise_noop):
    """When notify() reports failure, the buffer is kept for the next attempt."""
    appriser, _ = apprise_noop

    logger.error("Boom")
    assert len(appriser.buffer) == 1

    mocker.patch.object(appriser.apprise_obj, "notify", return_value=False)
    appriser.send_notification()

    assert len(appriser.buffer) == 1  # not cleared, since the send did not succeed


def test_intercept_skips_setup_for_already_handled_logger():
    """A logger already flagged as handled does not get the interceptor re-attached."""
    make_appriser()  # patches logging.Logger._log

    already_handled = logging.getLogger("test.already.handled")
    already_handled._has_been_handled_by_interceptor = True

    # Routes through the patched _log and takes the "skip setup" branch.
    already_handled.error("message")

    assert not any(isinstance(h, InterceptHandler) for h in already_handled.handlers)


def test_install_is_idempotent(mocker):
    """A second install() is a no-op and does not re-run the global side effects."""
    appriser = make_appriser()  # installs once

    spy = mocker.patch.object(appriser, "_setup_interception_handler")
    appriser.install()  # already armed -> early return

    spy.assert_not_called()


def test_config_file_loading(tmp_path, mocker):
    """Test that Appriser can load config from filesystem"""
    # Mock DEFAULT_CONFIG_PATHS to only use our temp directory
    config_path = tmp_path / "apprise.yml"
    mocker.patch("apprise.cli.DEFAULT_CONFIG_PATHS", [str(config_path)])

    # Create a temporary config file
    config_path.write_text("urls:\n      - mailto://localhost?from=me@local.be&to=you@local.be")

    appriser = make_appriser()
    # If config is loaded successfully, urls will be populated
    assert len(appriser.apprise_obj) == 1


def test_multiple_notification_batching(apprise_noop):
    """Test that multiple log messages get batched into single notification"""
    appriser, noop = apprise_noop

    # Generate logs over time
    logger.error("Error 1")
    logger.error("Error 2")
    logger.critical("Critical 1")
    logger.error("Error 3")

    # Send notification
    appriser.send_notification()

    # Should be one notification containing all messages
    assert len(noop.calls) == 1
    notification = noop.calls[0]
    assert "Error 1" in notification["body"]
    assert "Error 2" in notification["body"]
    assert "Critical 1" in notification["body"]
    assert "Error 3" in notification["body"]


def test_notification_level_changes():
    """Test changing notification levels and verifying correct message capture"""
    # Initialize with WARNING level
    appriser = make_appriser(apprise_trigger_level="WARNING")

    # First batch: WARNING level
    logger.info("Info message 1")
    logger.warning("Warning message 1")
    logger.error("Error message 1")

    assert len(appriser.buffer) == 2
    assert "Info message 1" not in [message.record["message"] for message in appriser.buffer]
    assert "Warning message 1" in [message.record["message"] for message in appriser.buffer]
    assert "Error message 1" in [message.record["message"] for message in appriser.buffer]

    # Clear buffer
    appriser.buffer.clear()

    # Change to ERROR level
    appriser.notification_level = "ERROR"
    logger.info("Info message 2")
    logger.warning("Warning message 2")

    assert len(appriser.buffer) == 0

    # Change to INFO level
    appriser.notification_level = "INFO"
    logger.info("Info message 3")
    logger.warning("Warning message 3")

    assert len(appriser.buffer) == 2
    assert "Info message 3" in [message.record["message"] for message in appriser.buffer]
    assert "Warning message 3" in [message.record["message"] for message in appriser.buffer]


def test_notification_level_edge_cases():
    """Test edge cases for notification levels"""
    appriser = make_appriser()

    # Test setting levels in different formats
    appriser.notification_level = "DEBUG"  # string
    assert appriser.notification_level == logger.level("DEBUG").no

    appriser.notification_level = 30  # int (WARNING level)
    assert appriser.notification_level == logger.level("WARNING").no

    appriser.notification_level = logger.level("ERROR")  # Level object
    assert appriser.notification_level == logger.level("ERROR").no

    # Test invalid level
    with pytest.raises(TypeError):
        appriser.notification_level = None

    with pytest.raises(ValueError):
        appriser.notification_level = "INVALID_LEVEL"


def test_custom_log_level():
    """Test handling of custom log levels that don't map to loguru levels"""
    # Create a custom log level in standard logging
    custom_level_num = 15  # Between DEBUG and INFO
    custom_level_name = "CUSTOM"
    logging.addLevelName(custom_level_num, custom_level_name)

    # Set up standard logger with our custom level
    standard_logger = logging.getLogger("custom_test")
    standard_logger.setLevel(custom_level_num)

    # Create Appriser with low threshold to catch all messages
    appriser = make_appriser(apprise_trigger_level="DEBUG")

    # Log using our custom level
    standard_logger.log(custom_level_num, "Custom level message")

    # Verify the message was captured and level was handled appropriately
    assert len(appriser.buffer) == 1
    record = appriser.buffer[0].record
    # The level number should be preserved even if the name isn't in loguru
    assert record["level"].no == custom_level_num


def test_all_standard_levels():
    """Test all standard logging levels are handled correctly"""
    appriser = make_appriser(apprise_trigger_level="DEBUG")

    # Dictionary of standard logging levels and their expected loguru equivalents
    standard_levels = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO",
        logging.WARNING: "WARNING",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    # Test each standard level
    for level_no, level_name in standard_levels.items():
        logger.log(level_name, f"Test message for {level_name}")

        # Find the corresponding record
        matching_records = [r for r in appriser.buffer if r.record["level"].name == level_name]
        assert len(matching_records) == 1
        assert matching_records[0].record["level"].no == level_no

    # Verify total number of records
    assert len(appriser.buffer) == len(standard_levels)


def test_send_notification_parameters(mocker, apprise_noop):
    test_message = "Test log message"
    custom_title = "Custom Title"
    custom_type = "success"
    custom_format = NotifyFormat.MARKDOWN

    appriser, _noop = apprise_noop
    appriser.buffer.append(test_message)

    mock_notify = mocker.patch.object(appriser.apprise_obj, "notify")

    appriser.send_notification(title=custom_title, notify_type=custom_type, body_format=custom_format)

    mock_notify.assert_called_once_with(
        title=custom_title, notify_type=custom_type, body=test_message, body_format=custom_format
    )
    assert len(appriser.buffer) == 0


@pytest.mark.parametrize(
    "notify_type_param, notify_format_param",
    [
        # Using string values
        ("info", "text"),
        ("success", "markdown"),
        ("warning", "html"),
        ("failure", "text"),
        # Using Apprise enum objects
        (NotifyType.INFO, NotifyFormat.TEXT),
        (NotifyType.SUCCESS, NotifyFormat.MARKDOWN),
        (NotifyType.WARNING, NotifyFormat.HTML),
        (NotifyType.FAILURE, NotifyFormat.TEXT),
        # Mixed: string type with enum format and vice versa
        ("info", NotifyFormat.HTML),
        (NotifyType.SUCCESS, "markdown"),
    ],
)
def test_notification_parameter_types(mocker, apprise_noop, notify_type_param, notify_format_param):
    """Test that Appriser accepts different parameter types for notify_type and body_format"""
    test_message = "Test log message"
    custom_title = "Custom Title"

    appriser, _noop = apprise_noop
    appriser.buffer.append(test_message)

    mock_notify = mocker.patch.object(appriser.apprise_obj, "notify")

    # Call with the parametrized values
    appriser.send_notification(title=custom_title, notify_type=notify_type_param, body_format=notify_format_param)

    # Verify the parameters were passed through correctly
    mock_notify.assert_called_once_with(
        title=custom_title, notify_type=notify_type_param, body=test_message, body_format=notify_format_param
    )

    assert len(appriser.buffer) == 0


def test_intercepted_logger_doesnt_output_its_messages(capsys) -> None:
    """Test that standard logging messages do NOT get outputed in the console"""

    # Configure standard logging to use our handler -- this will set up a chain
    l1 = logging.getLogger("test")
    l1.addHandler(NullHandler())
    l2 = logging.getLogger("test.logger")
    l2.addHandler(StreamHandler())
    l3 = logging.getLogger("test.logger.sublogger")
    # Create an Appriser to capture the logs
    appriser = make_appriser()

    # Log using standard logging
    test_message = "Test log message"
    l3.error(test_message)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    # Verify the message was captured by our appriser
    assert len(appriser.buffer) == 1
    assert appriser.buffer[0].record["message"] == test_message
    assert appriser.buffer[0].record["level"].name == "ERROR"


def test_intercepted_logger_has_streamhandler(capsys) -> None:
    """Test that standard logging messages do NOT get outputed in the console"""

    # Configure standard logging to use our handler -- this will set up a chain
    _log = logging.getLogger("test")
    _log.addHandler(StreamHandler())

    # Create an Appriser to capture the logs
    appriser = make_appriser()

    # Log using standard logging
    test_message = "Test log message"
    _log.error(test_message)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    # Verify the message was captured by our appriser
    assert len(appriser.buffer) == 1
    assert appriser.buffer[0].record["message"] == test_message
    assert appriser.buffer[0].record["level"].name == "ERROR"
