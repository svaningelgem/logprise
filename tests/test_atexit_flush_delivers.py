"""End-to-end check that the atexit flush actually delivers (#166).

Spawns a real python subprocess so ``atexit`` fires during interpreter
shutdown, with two targets so apprise would reach for its thread pool. Each
target appends a line to a sentinel file when it sends.
"""

import subprocess
import sys
import textwrap
from pathlib import Path


def test_atexit_flush_delivers_to_every_target(tmp_path: Path) -> None:
    sentinel = tmp_path / "delivered.txt"
    script = tmp_path / "log_error_and_exit.py"
    script.write_text(
        textwrap.dedent(
            f"""\
            from pathlib import Path

            import apprise
            from apprise import NotifyBase, NotifyType

            from logprise import appriser, logger

            _SENTINEL = Path({sentinel.as_posix()!r})


            class Sentinel(NotifyBase):
                secure_protocol = False
                protocol = ("sentinel",)

                def __init__(self, **kwargs):
                    super().__init__(secure=False, **kwargs)

                def url(self, privacy=False, *args, **kwargs):
                    return "sentinel://"

                def send(self, body, title="", notify_type=NotifyType.INFO, **kwargs):
                    with _SENTINEL.open("a") as fh:
                        print("delivered", file=fh)
                    return True


            appriser.apprise_obj = apprise.Apprise()  # ignore any real config on this machine
            appriser.add(Sentinel())
            appriser.add(Sentinel())  # two targets: apprise would use a thread pool

            logger.error("delivered at exit?")
            """
        )
    )

    result = subprocess.run([sys.executable, script], capture_output=True, text=True, check=True)

    assert "Failed to send notification" not in result.stderr
    assert sentinel.read_text().count("delivered") == 2
