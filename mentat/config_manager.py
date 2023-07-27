import json
import logging
import os
from importlib import resources
from pathlib import Path

mentat_dir_path = os.path.join(Path.home(), ".mentat")

# package_name should always be "mentat" - but this will work if package name is changed
package_name = __name__.split(".")[0]
config_file_name = "default_config.json"
user_config_file_name = "config.json"
user_config_path = os.path.join(mentat_dir_path, user_config_file_name)


class ConfigManager:
    def __init__(self):
        if os.path.exists(user_config_path):
            with open(user_config_path) as config_file:
                self.user_config = json.load(config_file)
        else:
            self.user_config = {}
        with resources.files(package_name).joinpath(config_file_name).open(
            "r"
        ) as config_file:
            self.default_config = json.load(config_file)

    def input_style(self) -> list[list[str]]:
        return self._get_key("input-style")

    def allow_32k(self) -> bool:
        return self._get_key("allow-32k")

    def filetype_include_list(self) -> list[str]:
        return self._get_key("filetype-include-list")

    def filetype_exclude_list(self) -> list[str]:
        return self._get_key("filetype-exclude-list")

    def file_exclude_glob_list(self) -> list[str]:
        return self._get_key("file-exclude-glob-list")

    def _get_key(self, key: str):
        if key in self.user_config:
            return self.user_config[key]
        elif key in self.default_config:
            return self.default_config[key]
        else:
            logging.warning(f"No value for config key {key} found")
            return None
