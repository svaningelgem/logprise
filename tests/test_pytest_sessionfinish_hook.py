"""End-to-end check that the pytest plugin clears the buffer at session finish.

Spawns a real pytest subprocess so ``atexit`` actually fires. The inline test
file registers its own ``atexit`` handler *after* importing logprise, so by
LIFO order that handler runs *before* :meth:`Appriser.cleanup` -- capturing
``len(appriser.buffer)`` at the moment cleanup is about to flush.

If the ``pytest_sessionfinish`` wrapper hook in ``logprise.pytest_plugin`` did
its job, the buffer is empty by then and the sentinel file reads ``"0"``.
"""

import subprocess
import sys
import textwrap
from pathlib import Path


def test_sessionfinish_clears_buffer(tmp_path: Path) -> None:
    sentinel = tmp_path / "buffer_len.txt"
    test_file = tmp_path / "test_emits_error.py"
    test_file.write_text(
        textwrap.dedent(
            f"""\
            import atexit
            from pathlib import Path

            import apprise

            from logprise import appriser, logger

            # Defend against a developer machine with real apprise config: if the
            # sessionfinish hook ever regresses, this keeps the subprocess from
            # paging via real services. The buffer-length sentinel below is the
            # actual signal we measure.
            appriser.apprise_obj = apprise.Apprise()

            _SENTINEL = Path({sentinel.as_posix()!r})


            def _record_buffer_state() -> None:
                _SENTINEL.write_text(str(len(appriser.buffer)))


            # Registered AFTER logprise's own atexit(cleanup) -> fires FIRST in
            # LIFO order, capturing the buffer state at the moment cleanup is
            # about to run.
            atexit.register(_record_buffer_state)


            def test_emits_error() -> None:
                logger.error("boom")
            """
        )
    )

    subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert sentinel.read_text() == "0", (
        f"Expected appriser.buffer empty at atexit (sessionfinish hook ran); got {sentinel.read_text()!r}"
    )
