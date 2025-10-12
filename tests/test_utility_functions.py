import sysconfig
from pathlib import Path
from types import ModuleType

from logprise import Appriser


def test_no_module_found(mocker):
    """When inspect.getmodule returns None"""
    mocker.patch("inspect.getmodule", return_value=None)
    assert Appriser._is_method_in_stdlib(lambda: None) is False


def test_stdlib_builtin_function():
    """Builtin functions are from stdlib"""
    assert Appriser._is_method_in_stdlib(len) is True
    assert Appriser._is_method_in_stdlib(print) is True


def test_stdlib_module_function():
    """Functions from stdlib modules"""
    assert Appriser._is_method_in_stdlib(Path.resolve) is True


def test_backport_module(mocker):
    """Modules in _STDLIB_BACKPORTS are treated as stdlib"""

    def func():
        return None

    func.__module__ = "tomli.parser"

    mock_module = ModuleType("tomli")
    mock_module.__file__ = "/some/path/tomli.py"
    mocker.patch("inspect.getmodule", return_value=mock_module)

    assert Appriser._is_method_in_stdlib(func) is True


def test_module_without_file_attribute(mocker):
    """Modules without __file__ are treated as stdlib"""

    def func():
        return None

    func.__module__ = "some_module"

    mock_module = ModuleType("some_module")
    mocker.patch("inspect.getmodule", return_value=mock_module)

    assert Appriser._is_method_in_stdlib(func) is True


def test_site_packages_module(mocker):
    """Modules from site-packages are not stdlib"""

    def func():
        return None

    func.__module__ = "external_package"

    mock_module = ModuleType("external_package")
    mock_module.__file__ = "/usr/lib/python3.10/site-packages/package.py"
    mocker.patch("inspect.getmodule", return_value=mock_module)

    assert Appriser._is_method_in_stdlib(func) is False


def test_dist_packages_module(mocker):
    """Modules from dist-packages are not stdlib"""

    def func():
        return None

    func.__module__ = "external_package"

    mock_module = ModuleType("external_package")
    mock_module.__file__ = "/usr/lib/python3.10/dist-packages/package.py"
    mocker.patch("inspect.getmodule", return_value=mock_module)

    assert Appriser._is_method_in_stdlib(func) is False


def test_module_in_stdlib_path(mocker):
    """Modules in stdlib paths are from stdlib"""

    def func():
        return None

    func.__module__ = "custom_module"

    stdlib_path = sysconfig.get_paths()["stdlib"]
    mock_module = ModuleType("custom_module")
    mock_module.__file__ = str(Path(stdlib_path) / "custom_module.py")
    mocker.patch("inspect.getmodule", return_value=mock_module)

    assert Appriser._is_method_in_stdlib(func) is True


def test_third_party_module(mocker):
    """Regular third-party modules are not stdlib"""

    def func():
        return None

    func.__module__ = "mypackage"

    mock_module = ModuleType("mypackage")
    mock_module.__file__ = "/home/user/project/mypackage.py"
    mocker.patch("inspect.getmodule", return_value=mock_module)

    assert Appriser._is_method_in_stdlib(func) is False
