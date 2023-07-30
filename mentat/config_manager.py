import json
import logging
import os
from importlib import resources
from json import JSONDecodeError
from pathlib import Path

from termcolor import cprint

mentat_dir_path = os.path.join(Path.home(), ".mentat")

# package_name should always be "mentat" - but this will work if package name is changed
package_name = __name__.split(".")[0]
default_config_file_name = "default_config.json"
config_file_name = ".mentat_config.json"
user_config_path = os.path.join(mentat_dir_path, config_file_name)

# Remove this warning after August 19
old_config_file_path = os.path.join(mentat_dir_path, "config.json")


class ConfigManager:
    def __init__(self, git_root: str):
        # Remove this warning after August 19
        if os.path.exists(old_config_file_path):
            cprint(
                "Warning: You are still using an old config.json in your ~/.mentat"
                " directory. The config filename has recently been changed to"
                " .mentat_config.json, and can be present in either ~/.mentat or the"
                " git project you are working in. Your current config.json file will"
                " not be used.",
                color="light_yellow",
            )

        if os.path.exists(user_config_path):
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
                    self.user_config = {}
        else:
            self.user_config = {}

        project_config_path = os.path.join(git_root, config_file_name)
        if os.path.exists(project_config_path):
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
                    self.project_config = {}
        else:
            self.project_config = {}

        default_config_path = resources.files(package_name).joinpath(
            default_config_file_name
        )
        with default_config_path.open("r") as config_file:
            self.default_config = json.load(config_file)

    def input_style(self) -> list[list[str]]:
        return self._get_key("input-style")

    def allow_32k(self) -> bool:
        return self._get_key("allow-32k")

    def file_exclude_glob_list(self) -> list[str]:
        return self._get_key("file-exclude-glob-list")

    def _get_key(self, key: str):
        if key in self.project_config:
            return self.project_config[key]
        elif key in self.user_config:
            return self.user_config[key]
        elif key in self.default_config:
            return self.default_config[key]
        else:
            raise ValueError(f"No value for config key {key} found")
