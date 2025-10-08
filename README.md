# Logprise

Logprise provides a one-stop logger for your Python application by integrating [loguru](https://github.com/Delgan/loguru/) and [apprise](https://github.com/caronc/apprise). It intercepts all standard `logging` calls and routes them through a unified interface. Above a configurable threshold, errors are automatically sent as alerts via Slack, Discord, email, or 100+ other services - no code changes needed.

## Why Logprise?

Your script crashes at 3 AM. You want to know about it immediately, not when you check logs tomorrow. Logprise automatically captures errors and sends them to your notification service of choice.

**Works with your existing code:** Logprise intercepts standard Python `logging` calls and redirects them through loguru. No need to refactor your codebase or update third-party libraries.

```python
from logprise import logger
import logging

logger.error("Payment processing failed")  # You get notified
logging.error("Database connection lost")  # Also notified (auto-intercepted)
logger.warning("High memory usage")        # Silent (unless configured)
```

## Installation

```bash
pip install logprise
```

## Quick Start

**Step 1:** Configure notification service (create `~/.apprise` file):

```text
mailto://user:pass@gmail.com
```

**Step 2:** Use it in your code:

```python
from logprise import logger

logger.info("Script started")
logger.error("This triggers a notification")  # Sent when program exits or after 1 hour
```

That's it. Errors automatically trigger notifications. No configuration needed beyond setting up your notification service.

## Configuration

### Notification Services

Apprise supports 100+ services. Configure them in `~/.apprise` (or other [standard locations](https://github.com/caronc/apprise/blob/master/apprise/cli.py)):

```text
# Email
mailto://user:pass@gmail.com

# Slack
slack://tokenA/tokenB/tokenC/#channel

# Discord
discord://webhook_id/webhook_token

# Telegram
tgram://bot_token/chat_id
```

See [Apprise's service list](https://github.com/caronc/apprise/wiki) for all options.

You can also add services programmatically:

```python
from logprise import appriser

appriser.add("mailto://user:pass@gmail.com")
appriser.add(["slack://token/...", "discord://webhook/..."])
```

### Notification Level

Control which log levels trigger notifications:

```python
from logprise import appriser

appriser.notification_level = "WARNING"  # Notify on WARNING and above
appriser.notification_level = "CRITICAL" # Only critical issues
appriser.notification_level = 30         # Numeric levels work too
```

Default is ERROR (30).

### Timing Control

Notifications batch to prevent spam. Control when they're sent:

```python
from logprise import appriser

# Change flush interval (default: 3600 seconds)
appriser.flush_interval = 1800  # Send every 30 minutes

# Send immediately
appriser.send_notification()

# Clear pending notifications without sending
appriser.buffer.clear()
```

Notifications automatically flush when your program exits.

## Use Cases

**Long-running scripts:**
```python
from logprise import logger

for item in large_dataset:
    try:
        process(item)
    except Exception as e:
        logger.error(f"Failed processing {item}: {e}")
        # Notification sent, script continues
```

**Scheduled jobs:**
```python
from logprise import logger, appriser

appriser.notification_level = "INFO"  # Get notified of completion too

def daily_backup():
    logger.info("Backup started")
    # ... backup logic ...
    logger.info("Backup completed")
```

**Monitoring critical sections:**
```python
from logprise import logger

if disk_usage > 90:
    logger.critical(f"Disk usage at {disk_usage}%")
    # Immediate notification on program exit
```

**Works with third-party libraries:**
```python
from logprise import logger
import requests
import logging

# Third-party libraries using standard logging are automatically captured
response = requests.get("https://api.example.com")
# If requests logs an error, you'll be notified

# Your existing logging code works too
logging.error("Custom error from standard logging")
logger.error("Error from loguru")
# Both trigger notifications
```

## How It Works

1. **Automatic interception:** Logprise intercepts both loguru and standard library `logging`, redirecting all logs through a unified interface
2. **Smart batching:** Messages accumulate until flush interval or program exit
3. **Exception capture:** Uncaught exceptions are logged and trigger immediate notification
4. **Multiple services:** Send to multiple notification services simultaneously

This means third-party libraries using standard `logging` will also trigger notifications when they log errors.

## Advanced Features

**Prevent handler removal:**
```python
from logprise import logger

logger.remove()  # Logprise handler persists automatically
```

**Tagging for routing:**
```python
from logprise import appriser

appriser.add("discord://webhook/...", tag=["critical"])
appriser.add("mailto://...", tag=["all"])
```

**Custom notification format:**
```python
from logprise import appriser
from apprise import NotifyType, NotifyFormat

appriser.send_notification(
    title="Production Alert",
    notify_type=NotifyType.FAILURE,
    body_format=NotifyFormat.MARKDOWN
)
```

## Contributing

```bash
git clone https://github.com/svaningelgem/logprise.git
cd logprise
poetry install
poetry run pytest
```

Contributions welcome via pull requests.

## License

MIT License - see LICENSE file for details.
