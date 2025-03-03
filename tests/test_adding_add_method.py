from logprise import Appriser


def test_add_method(mocker):
    """Test that add method correctly passes through to apprise_obj.add"""
    appriser = Appriser()

    # Create a mock for the underlying apprise_obj.add method
    mock_add = mocker.patch.object(appriser.apprise_obj, 'add', return_value=True)

    # Test with a simple string URL
    test_url = "mailto://user:pass@example.com"
    assert appriser.add(test_url) is True

    # Verify add was called with correct parameters
    mock_add.assert_called_once_with(servers=test_url, asset=None, tag=None)

    # Reset mock for next test
    mock_add.reset_mock()

    # Test with a dictionary
    test_dict = {"urls": ["mailto://user:pass@example.com"]}
    test_tag = ["important"]
    assert appriser.add(test_dict, tag=test_tag) is True

    # Verify add was called with correct parameters
    mock_add.assert_called_once_with(servers=test_dict, asset=None, tag=test_tag)

    # Test return value pass-through (False case)
    mock_add.return_value = False
    mock_add.reset_mock()

    assert appriser.add("invalid://url") is False
    mock_add.assert_called_once()
