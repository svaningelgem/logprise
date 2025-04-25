import pytest_mock

import logprise
from logprise import InterceptHandler


def test_ignore_intellij_in_stacktrace(mocker: pytest_mock.MockerFixture) -> None:
    sut = InterceptHandler()
    fake_frame = mocker.Mock(f_code=mocker.Mock(co_filename="some/jetbrains/intellij/file"))
    assert sut._should_ignore_this_frame(fake_frame) is True

def test_ignore_string_in_stacktrace(mocker: pytest_mock.MockerFixture) -> None:
    sut = InterceptHandler()
    fake_frame = mocker.Mock(f_code=mocker.Mock(co_filename="<string>"))
    assert sut._should_ignore_this_frame(fake_frame) is True

def test_ignore_current_logprise_file_in_stacktrace(mocker: pytest_mock.MockerFixture) -> None:
    sut = InterceptHandler()
    fake_frame = mocker.Mock(f_code=mocker.Mock(co_filename=logprise.__file__))
    assert sut._should_ignore_this_frame(fake_frame) is True
