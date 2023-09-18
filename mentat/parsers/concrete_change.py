from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Self

from mentat.code_file_manager import CodeFileManager
from mentat.config_manager import ConfigManager
from mentat.parsers.change_display_helper import DisplayInformation
from mentat.parsers.file_edit import FileEdit


class ConcreteChange(ABC):
    # TODO: Separate this out into a separate parsing class that can be injected
    # and will create a list of it's specific concrete change (will also return prompt examples etc.)
    @abstractmethod
    @classmethod
    async def stream_and_parse_llm_response(
        cls, response: AsyncGenerator[Any, None], code_file_manager: CodeFileManager
    ) -> tuple[str, list[Self]]:
        pass

    # TODO: Also put this in injectable parser
    @abstractmethod
    @classmethod
    def to_file_edits(
        cls,
        changes: list[Self],
        config: ConfigManager,
    ) -> list[FileEdit]:
        pass

    @abstractmethod
    def get_change_display_information(self) -> DisplayInformation:
        pass
