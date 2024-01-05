import base64
import os
from typing import Optional

import attr
from selenium import webdriver
from selenium.common.exceptions import NoSuchWindowException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.remote.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager

from mentat.session_context import SESSION_CONTEXT


class ScreenshotException(Exception):
    """
    Thrown when a screenshot is attempted before the browser is opened.
    """


@attr.define
class VisionManager:
    driver: Optional[WebDriver] = attr.field(default=None)

    def _open_browser(self) -> None:
        ctx = SESSION_CONTEXT.get()
        safari_installed = False
        if self.driver is None or not self.driver_running():
            try:
                self.driver = webdriver.Safari()
            except Exception as e:
                if "remote automation" in str(e).lower():
                    safari_installed = True
                try:
                    service = Service(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service)
                except Exception:
                    try:
                        service = EdgeService(EdgeChromiumDriverManager().install())
                        self.driver = webdriver.Edge(service=service)
                    except Exception:
                        try:
                            service = FirefoxService(GeckoDriverManager().install())
                            self.driver = webdriver.Firefox(service=service)
                        except Exception:
                            if safari_installed:
                                ctx.stream.send(
                                    "No suitable browser found. To use Safari, enable"
                                    " remote automation.",
                                    style="error",
                                )
                            else:
                                ctx.stream.send(
                                    "No suitable browser found.",
                                    style="error",
                                )

                            raise ScreenshotException()

    def open(self, path: str) -> None:
        self._open_browser()
        self.driver.get(path)  # type: ignore

    def driver_running(self):
        try:
            # This command should fail if the driver is not running
            self.driver.execute_script('return "hello world";')  # type: ignore
            return True
        except NoSuchWindowException:
            return False

    def screenshot(self, path: Optional[str] = None) -> str:
        ctx = SESSION_CONTEXT.get()
        if path is not None:
            expanded = os.path.abspath(os.path.expanduser(path))
            browser_path = path
            if os.path.exists(expanded):
                browser_path = "file://" + expanded
            else:
                if not path.startswith("http"):
                    browser_path = "https://" + path
            try:
                self.open(browser_path)
            except WebDriverException:
                ctx.stream.send(
                    f"Error taking screenshot. Is {path} a valid url or local file?",
                    style="error",
                )
                raise ScreenshotException()
        else:
            if self.driver is None:
                ctx.stream.send(
                    'No browser open. Run "/screenshot path" with a url or local file',
                    style="error",
                )
                raise ScreenshotException()

        screenshot_data = self.driver.get_screenshot_as_png()  # type: ignore

        decoded = base64.b64encode(screenshot_data).decode("utf-8")
        image_data = f"data:image/png;base64,{decoded}"

        return image_data

    def close(self) -> None:
        if self.driver is not None:
            self.driver.quit()
