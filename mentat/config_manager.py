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

    def filepath_include_only_these_regex_patterns(self) -> list[str]:
        return self._get_key("filepath-include-only-these-regex-patterns", False)
    
    def filepath_exclude_these_regex_patterns(self) -> list[str]:
        return self._get_key("filepath-exclude-these-regex-patterns", False)

    def do_not_check_git_ignore(self) -> bool:
        return self._get_key("do-not-check-git-ignore", False)

    def _get_key(self, key: str, is_required = True):
        if key in self.user_config:
            return self.user_config[key]
        elif key in self.default_config:
            return self.default_config[key]
        elif is_required:
            logging.error(f"No value for config key {key} found")
        return None
