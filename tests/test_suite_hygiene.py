"""The suite must not leave armed Appriser instances behind or touch the host's apprise config."""

import atexit

from conftest import dispose, make_appriser


def test_dispose_stops_the_flush_thread_and_unregisters_atexit(mocker):
    unregister = mocker.spy(atexit, "unregister")
    appriser = make_appriser()
    assert appriser._flush_thread.is_alive()

    dispose(appriser)

    assert not appriser._flush_thread.is_alive()
    unregister.assert_called_once_with(appriser.cleanup)
