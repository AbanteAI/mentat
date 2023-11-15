import datetime
import os
from pathlib import Path

import attr
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from mentat.utils import mentat_dir_path


@attr.define
class VisionManager:
    driver: webdriver.Chrome | None = attr.field(default=None)

    def init(self) -> None:
        "This opens a browser with no page open so we don't want to call it until the user actually wants it."
        if self.driver is None:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service)

    def open(self, path: str) -> None:
        self.init()
        self.driver.get(path)  # type: ignore

    def screenshot(self, path: str) -> Path:
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded):
            path = "file://" + expanded
        else:
            if not path.startswith("http"):
                path = "https://" + path
        self.open(path)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = (
            timestamp
            + "_"
            + path.replace("https://", "")
            .replace("http://", "")
            .replace("/", "_")
            .replace(".", "_")
            + ".png"
        )
        dir_path = mentat_dir_path / "screenshots"
        dir_path.mkdir(parents=True, exist_ok=True)
        image_path = dir_path / name
        self.driver.save_screenshot(image_path)  # type: ignore
        return image_path
