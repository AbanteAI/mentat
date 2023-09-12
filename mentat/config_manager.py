import json
import logging
from importlib import resources
from json import JSONDecodeError
from pathlib import Path
from typing import Any, cast

from termcolor import cprint

mentat_dir_path = Path.home() / ".mentat"

# package_name should always be "mentat" - but this will work if package name is changed
package_name = __name__.split(".")[0]
default_config_file_name = "default_config.json"
config_file_name = ".mentat_config.json"
user_config_path = mentat_dir_path / config_file_name


class ConfigManager:
    def __init__(self, git_root: Path):
        self.git_root = git_root

        if user_config_path.exists():
            with open(user_config_path) as config_file:
                try:
                    self.user_config = json.load(config_file)
                except JSONDecodeError:
                    logging.info("User config file contains invalid json")
                    cprint(
                        "Warning: User .mentat_config.json contains invalid"
                        " json; ignoring user configuration file",
                        "light_yellow",
                    )
                    self.user_config = dict[str, str]()
        else:
            self.user_config = dict[str, str]()

        project_config_path = self.git_root / config_file_name
        if project_config_path.exists():
            with open(project_config_path) as config_file:
                try:
                    self.project_config = json.load(config_file)
                except JSONDecodeError:
                    logging.info("Project config file contains invalid json")
                    cprint(
                        "Warning: Git project .mentat_config.json contains invalid"
                        " json; ignoring project configuration file",
                        "light_yellow",
                    )
                    self.project_config = dict[str, str]()
        else:
            self.project_config = dict[str, str]()

        default_config_path = resources.files(package_name).joinpath(
            default_config_file_name
        )
        with default_config_path.open("r") as config_file:
            self.default_config = json.load(config_file)

    def input_style(self) -> list[tuple[str, str]]:
        return cast(list[tuple[str, str]], self._get_key("input-style"))

    def allow_32k(self) -> bool:
        return cast(bool, self._get_key("allow-32k"))

    def file_exclude_glob_list(self) -> list[str]:
        return cast(list[str], self._get_key("file-exclude-glob-list"))

    def _get_key(self, key: str) -> Any:
        if key in self.project_config:
            return self.project_config[key]
        elif key in self.user_config:
            return self.user_config[key]
        elif key in self.default_config:
            return self.default_config[key]
        else:
            raise ValueError(f"No value for config key {key} found")
