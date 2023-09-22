from pathlib import Path
from typing import Any, AsyncGenerator

from typing_extensions import override

from mentat.code_file_manager import CodeFileManager
from mentat.config_manager import ConfigManager
from mentat.parsers.file_edit import FileEdit
from mentat.parsers.original_format.original_format_parsing import (
    stream_and_parse_llm_response,
)
from mentat.parsers.parser import Parser
from mentat.prompts.prompts import read_prompt

block_parser_prompt_filename = Path("block_parser_prompt.txt")


class BlockParser(Parser):
    @override
    def get_system_prompt(self) -> str:
        return read_prompt(block_parser_prompt_filename)

    @override
    async def stream_and_parse_llm_response(
        self,
        response: AsyncGenerator[Any, None],
        code_file_manager: CodeFileManager,
        config: ConfigManager,
    ) -> tuple[str, list[FileEdit]]:
        # Uses the legacy parsing code
        return await stream_and_parse_llm_response(
            response, code_file_manager, config, self.shutdown
        )
