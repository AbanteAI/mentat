from unittest.mock import MagicMock, patch

import pytest

from mentat.vision.vision_manager import ScreenshotException, VisionManager


@pytest.fixture
def mock_webdriver():
    with patch("selenium.webdriver.Safari") as mock:
        yield mock


@pytest.fixture
def mock_platform():
    with patch("platform.system") as mock:
        yield mock


def test_vision_manager_screenshot(mock_platform, mock_webdriver, temp_testbed):
    mock_driver_instance = MagicMock()
    mock_webdriver.return_value = mock_driver_instance

    mock_platform.return_value = "Darwin"
    mock_driver_instance.get_screenshot_as_png.return_value = b"fake_screenshot_data"

    vision_manager = VisionManager()
    vision_manager._open_browser()

    # Test taking a screenshot of an opened page
    vision_manager.screenshot()
    mock_driver_instance.get_screenshot_as_png.assert_called_once()

    # Test taking a screenshot of a specific URL
    test_url = "http://example.com"
    vision_manager.screenshot(test_url)
    mock_driver_instance.get.assert_called_with(test_url)
    assert mock_driver_instance.get_screenshot_as_png.call_count == 2

    # Test taking a screenshot of a local file
    test_file_path = "scripts/calculator.py"
    vision_manager.screenshot(test_file_path)
    mock_driver_instance.get.assert_called_with(f"file://{temp_testbed / test_file_path}")
    assert mock_driver_instance.get_screenshot_as_png.call_count == 3

    # Test exception when no browser is open
    vision_manager.driver = None
    with pytest.raises(ScreenshotException):
        vision_manager.screenshot()
