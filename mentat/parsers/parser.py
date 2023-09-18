from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from mentat.code_file_manager import CodeFileManager
from mentat.config_manager import ConfigManager
from mentat.parsers.file_edit import FileEdit


class Parser(ABC):
    @abstractmethod
    def get_system_prompt(self) -> str:
        pass

    @abstractmethod
    async def stream_and_parse_llm_response(
        self,
        response: AsyncGenerator[Any, None],
        code_file_manager: CodeFileManager,
        config: ConfigManager,
    ) -> tuple[str, list[FileEdit]]:
        pass
