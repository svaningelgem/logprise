"""A failing test's report keeps its "Captured log call" section.

Spawns a real pytest run on a test that does not request ``caplog`` and logs
through both the standard library and loguru before failing. pytest's report
handler sits on the root logger, so both lines must show up there.
"""

import subprocess
import sys
import textwrap
from pathlib import Path


def test_failure_report_shows_logged_context(tmp_path: Path) -> None:
    test_file = tmp_path / "test_fails_after_logging.py"
    test_file.write_text(
        textwrap.dedent(
            """\
            import logging

            from logprise import logger


            def test_fails_after_logging():
                logging.getLogger("svc").warning("stdlib context line")
                logger.warning("loguru context line")
                assert False
            """
        )
    )

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q"], capture_output=True, text=True, check=False
    )

    assert result.returncode == 1
    assert "Captured log call" in result.stdout
    assert "stdlib context line" in result.stdout
    assert "loguru context line" in result.stdout
