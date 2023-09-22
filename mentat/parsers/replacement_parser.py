import asyncio
from pathlib import Path
from typing import Any, AsyncGenerator

from typing_extensions import override

from mentat.code_file_manager import CodeFileManager
from mentat.config_manager import ConfigManager
from mentat.llm_api import chunk_to_lines
from mentat.parsers.change_display_helper import (
    DisplayInformation,
    FileActionType,
    change_delimiter,
    get_file_name,
    get_later_lines,
    get_previous_lines,
    get_removed_lines,
)
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.parser import Parser
from mentat.prompts.prompts import read_prompt
from mentat.streaming_printer import StreamingPrinter

replacement_parser_prompt_filename = Path("replacement_parser_prompt.txt")


class ReplacementParser(Parser):
    @override
    def get_system_prompt(self) -> str:
        return read_prompt(replacement_parser_prompt_filename)

    @override
    async def stream_and_parse_llm_response(
        self,
        response: AsyncGenerator[Any, None],
        code_file_manager: CodeFileManager,
        config: ConfigManager,
    ) -> tuple[str, list[FileEdit]]:
        printer = StreamingPrinter()
        printer_task = asyncio.create_task(printer.print_lines())

        cur_line = ""
        cur_code_lines = ""
        cur_display_information: DisplayInformation | None = None
        new_line = True
        message = ""
        file_edits = dict[Path, FileEdit]()
        async for chunk in response:
            if self.shutdown.is_set():
                printer_task.cancel()
                break
            for content in chunk_to_lines(chunk):
                message += content
                cur_line += content
                if not cur_line.startswith("@"):
                    if cur_display_information is not None:
                        cur_code_lines += content
                        prefix = (
                            "+" + " " * (cur_display_information.line_number_buffer - 1)
                            if new_line
                            else ""
                        )
                        printer.add_string(prefix + content, end="", color="green")
                    else:
                        printer.add_string(content, end="")

                if "\n" in cur_line:
                    if cur_line.startswith("@"):
                        previous_file = None
                        if cur_display_information is not None:
                            previous_file = cur_display_information.file_name
                            if (
                                cur_display_information.file_action_type
                                == FileActionType.UpdateFile
                            ):
                                printer.add_string(
                                    get_removed_lines(cur_display_information)
                                )
                                printer.add_string(
                                    get_later_lines(cur_display_information)
                                )
                                printer.add_string(change_delimiter)

                                if (
                                    cur_display_information.first_changed_line
                                    is not None
                                    and cur_display_information.last_changed_line
                                    is not None
                                ):
                                    file_edits[
                                        cur_display_information.file_name
                                    ].replacements.append(
                                        Replacement(
                                            cur_display_information.first_changed_line,
                                            cur_display_information.last_changed_line,
                                            # The newline directly before the final @ symbol needs to be removed
                                            cur_code_lines.split("\n")[:-1],
                                        )
                                    )

                        cur_code_lines = ""
                        cur_display_information = self._process_special_line(
                            code_file_manager, cur_line
                        )
                        if cur_display_information is not None:
                            if (
                                cur_display_information.file_name != previous_file
                                or cur_display_information.file_action_type
                                == FileActionType.RenameFile
                            ):
                                printer.add_string(
                                    get_file_name(cur_display_information)
                                )
                                if (
                                    cur_display_information.file_action_type
                                    == FileActionType.UpdateFile
                                ):
                                    printer.add_string(change_delimiter)
                                    printer.add_string(
                                        get_previous_lines(cur_display_information)
                                    )

                            if cur_display_information.file_name not in file_edits:
                                file_edits[cur_display_information.file_name] = (
                                    FileEdit(cur_display_information.file_name)
                                )

                            match cur_display_information.file_action_type:
                                case FileActionType.CreateFile:
                                    file_edits[
                                        cur_display_information.file_name
                                    ].is_creation = True
                                case FileActionType.DeleteFile:
                                    file_edits[
                                        cur_display_information.file_name
                                    ].is_deletion = True
                                case FileActionType.RenameFile:
                                    file_edits[
                                        cur_display_information.file_name
                                    ].rename_file_path = (
                                        cur_display_information.new_name
                                    )
                                case _:
                                    pass

                    new_line = True
                    cur_line = ""
                else:
                    new_line = False
        else:
            printer.wrap_it_up()
            await printer_task

        return (message, [file_edit for file_edit in file_edits.values()])

    def _process_special_line(
        self, code_file_manager: CodeFileManager, special_line: str
    ) -> DisplayInformation | None:
        info = special_line.strip().split(" ")[1:]
        if len(info) == 0:
            return None
        file_name = Path(info[0])
        file_lines = code_file_manager.file_lines[file_name]
        if len(info) == 2:
            new_name = None
            match info[1]:
                case "+":
                    file_action_type = FileActionType.CreateFile
                case "-":
                    file_action_type = FileActionType.DeleteFile
                case _:
                    file_action_type = FileActionType.RenameFile
                    new_name = Path(info[1])
            return DisplayInformation(
                file_name, file_lines, [], [], file_action_type, new_name=new_name
            )
        elif len(info) == 3:
            # Convert from 1-index to 0-index
            starting_line = int(info[1]) - 1
            ending_line = int(info[2]) - 1
            file_action_type = FileActionType.UpdateFile
            return DisplayInformation(
                file_name,
                file_lines,
                [],
                file_lines[starting_line:ending_line],
                file_action_type,
                starting_line,
                ending_line,
            )
        else:
            return None
