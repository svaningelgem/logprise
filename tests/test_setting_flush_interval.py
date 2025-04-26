import pytest
import pytest_mock

from logprise import Appriser


def test_appriser_flush_interval_setter(mocker: pytest_mock.MockerFixture):
    """Test setting a valid flush interval."""
    appriser = Appriser(flush_interval=123)
    stop_periodic_flush_mock = mocker.patch.object(appriser, "stop_periodic_flush")
    start_periodic_flush_mock = mocker.patch.object(appriser, "_start_periodic_flush")

    assert appriser.flush_interval == 123
    stop_periodic_flush_mock.assert_not_called()
    start_periodic_flush_mock.assert_not_called()

    new_interval = 456
    appriser.flush_interval = new_interval
    assert appriser.flush_interval == new_interval
    stop_periodic_flush_mock.assert_called_once()
    start_periodic_flush_mock.assert_called_once()


def test_appriser_flush_interval_set_to_same_value(mocker: pytest_mock.MockerFixture):
    """Test setting the flush interval to the same value."""
    appriser = Appriser(flush_interval=123)
    stop_periodic_flush_mock = mocker.patch.object(appriser, "stop_periodic_flush")
    start_periodic_flush_mock = mocker.patch.object(appriser, "_start_periodic_flush")

    assert appriser.flush_interval == 123
    stop_periodic_flush_mock.assert_not_called()
    start_periodic_flush_mock.assert_not_called()

    appriser.flush_interval = 123
    assert appriser.flush_interval == 123
    stop_periodic_flush_mock.assert_not_called()
    start_periodic_flush_mock.assert_not_called()

@pytest.mark.parametrize("interval", [0, -1, -100, "invalid", None])
def test_appriser_flush_interval_setter_invalid(mocker: pytest_mock.MockerFixture, interval: int | float | str | None):
    """Test setting an invalid flush interval."""
    appriser = Appriser()
    stop_periodic_flush_mock = mocker.patch.object(appriser, "stop_periodic_flush")
    start_periodic_flush_mock = mocker.patch.object(appriser, "_start_periodic_flush")

    with pytest.raises(ValueError, match="Flush interval must be a positive number"):
        appriser.flush_interval = interval

    stop_periodic_flush_mock.assert_not_called()
    start_periodic_flush_mock.assert_not_called()
