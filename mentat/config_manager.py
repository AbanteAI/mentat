from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from importlib import resources
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, Optional, cast

from mentat.git_handler import GIT_ROOT
from mentat.session_stream import SESSION_STREAM

mentat_dir_path = Path.home() / ".mentat"

# package_name should always be "mentat" - but this will work if package name is changed
package_name = __name__.split(".")[0]
default_config_file_name = "default_config.json"
config_file_name = ".mentat_config.json"
user_config_path = mentat_dir_path / config_file_name

CONFIG_MANAGER: ContextVar[ConfigManager] = ContextVar("mentat:config_manager")


class ConfigManager:
    def __init__(
        self,
        user_config: Dict[str, str],
        project_config: Dict[str, str],
    ):
        self.user_config = user_config
        self.project_config = project_config

        default_config_path = resources.files(package_name).joinpath(
            default_config_file_name
        )
        with default_config_path.open("r") as config_file:
            self.default_config = json.load(config_file)

    @classmethod
    async def create(cls):
        stream = SESSION_STREAM.get()

        if user_config_path.exists():
            with open(user_config_path) as config_file:
                try:
                    user_config = json.load(config_file)
                except JSONDecodeError:
                    logging.info("User config file contains invalid json")
                    await stream.send(
                        "Warning: User .mentat_config.json contains invalid"
                        " json; ignoring user configuration file",
                        color="light_yellow",
                    )
                    user_config = dict[str, str]()
        else:
            user_config = dict[str, str]()

        project_config_path = GIT_ROOT.get() / config_file_name
        if project_config_path.exists():
            with open(project_config_path) as config_file:
                try:
                    project_config = json.load(config_file)
                except JSONDecodeError:
                    logging.info("Project config file contains invalid json")
                    await stream.send(
                        "Warning: Git project .mentat_config.json contains invalid"
                        " json; ignoring project configuration file",
                        color="light_yellow",
                    )
                    project_config = dict[str, str]()
        else:
            project_config = dict[str, str]()

        self = cls(user_config, project_config)

        return self

    def input_style(self) -> list[tuple[str, str]]:
        return cast(list[tuple[str, str]], self._get_key("input-style"))

    def model(self) -> str:
        return cast(str, self._get_key("model"))

    def maximum_context(self) -> Optional[int]:
        maximum_context = self._get_key("maximum-context")
        if maximum_context:
            return int(maximum_context)
        return None

    def file_exclude_glob_list(self) -> list[str]:
        return cast(list[str], self._get_key("file-exclude-glob-list"))

    def parser(self) -> str:
        return cast(str, self._get_key("format"))

    def _get_key(self, key: str) -> Any:
        if key in self.project_config:
            return self.project_config[key]
        elif key in self.user_config:
            return self.user_config[key]
        elif key in self.default_config:
            return self.default_config[key]
        else:
            raise ValueError(f"No value for config key {key} found")
