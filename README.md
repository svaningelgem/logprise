# Logprise

Logprise is a Python package that seamlessly integrates [loguru](https://github.com/Delgan/loguru/) and [apprise](https://github.com/caronc/apprise) to provide unified logging and notification capabilities. It allows you to automatically send notifications when specific log levels are triggered, making it perfect for monitoring applications and getting alerts when important events occur.

## Features

- Unified logging interface that captures both standard logging and loguru logs
- Automatic notification delivery based on configurable log levels
- Batched notifications to prevent notification spam
- Flexible configuration through apprises extensive notification service support
- Periodic flushing of log messages at configurable intervals
- Automatic capture of uncaught exceptions
- Easy integration with existing Python applications

## Installation

```bash
pip install logprise
```

Or if you're using Poetry:

```bash
poetry add logprise
```

## Quick Start

Here's a simple example of how to use Logprise:

```python
from logprise import logger

# Your logs will automatically trigger notifications
logger.info("This won't trigger a notification")
logger.warning("This won't trigger a notification")
logger.error("This will trigger a notification")  # Default is ERROR level

# Notifications are automatically sent when your program exits
# or periodically according to the flush interval
```

## Configuration

### Notification Services

Logprise uses Apprise for notifications, which supports a wide range of notification services. You can configure these in two ways:

#### 1. Configuration File

Create an `.apprise` file in one of the default configuration paths:

- `~/.apprise` \[or `%APPDATA%/Apprise/apprise`]
- `~/.config/apprise` \[or `%LOCALAPPDATA%/Apprise/apprise`]
- '/etc/apprise' \[or `%ALLUSERSPROFILE%/Apprise/apprise`]

*For more possible configuration file locations, please check: `DEFAULT_CONFIG_PATHS` in [apprises source code](https://github.com/caronc/apprise/blob/master/apprise/cli.py).*

Example configuration:

```text
mailto://user:pass@gmail.com
tgram://bot_token/chat_id
slack://tokenA/tokenB/tokenC/#channel
```

#### 2. Programmatically Add Services

You can easily add more notification services programmatically:

```python
from logprise import appriser

# Add a single URL
appriser.add("mailto://user:pass@gmail.com")

# Add multiple URLs
appriser.add(["tgram://bot_token/chat_id", "slack://tokenA/tokenB/tokenC/#channel"])

# Add URLs with tags
appriser.add("discord://webhook_id/webhook_token", tag=["critical"])
```

See [Apprise's configuration guide](https://github.com/caronc/apprise/wiki/config#cli) for the full list of supported services and their configuration.

### Notification Levels

You can set the minimum log level that triggers notifications:

```python
from logprise import appriser, logger

# Using string level names
appriser.notification_level = "WARNING"  # or "DEBUG", "INFO", "ERROR", "CRITICAL"

# Using integer level numbers
appriser.notification_level = 30  # WARNING level

# Using loguru Level objects
appriser.notification_level = logger.level("ERROR")
```

### Controlling Notification Timing

Logprise offers several ways to control when notifications are sent:

```python
from logprise import appriser

# Set the flush interval for periodic notifications (in seconds)
appriser.flush_interval = 3600  # Default is hourly

# Manually send notifications immediately
appriser.send_notification()

# Clear the notification buffer
appriser.buffer.clear()

# Stop the periodic flush thread
appriser.stop_periodic_flush()

# Manually cleanup and flush pending notifications
appriser.cleanup()
```

## Handling Uncaught Exceptions

Logprise automatically captures uncaught exceptions and sends notifications. This helps you detect and respond to unexpected application failures:

```python
# This will be logged and trigger a notification
raise ValueError("Something went wrong")
```

## Contributing

To contribute to the project:

```bash
# Clone the repository
git clone https://github.com/yourusername/logprise.git
cd logprise

# Install dependencies
poetry install

# Run tests
poetry run pytest
```

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.