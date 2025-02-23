# Logprise

Logprise is a Python package that seamlessly integrates [loguru](https://github.com/Delgan/loguru/) and [apprise](https://github.com/caronc/apprise) to provide unified logging and notification capabilities. It allows you to automatically send notifications when specific log levels are triggered, making it perfect for monitoring applications and getting alerts when important events occur.

## Features

- Unified logging interface that captures both standard logging and loguru logs
- Automatic notification delivery based on configurable log levels
- Batched notifications to prevent notification spam
- Flexible configuration through apprise's extensive notification service support
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
```

## Configuration

### Notification Services

Logprise uses Apprise for notifications, which supports a wide range of notification services. Create an `.apprise` file in one of the default configuration paths:

- `~/.apprise`
- `~/.config/apprise`

Example configuration:

```text
mailto://user:pass@gmail.com
tgram://bot_token/chat_id
slack://tokenA/tokenB/tokenC/#channel
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

### Manual Notification Control

While notifications are sent automatically when your program exits, you can control them manually:

```python
from logprise import appriser

# Clear the notification buffer
appriser.buffer.clear()

# Send notifications immediately
appriser.send_notification()
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