from enum import Enum
from pathlib import Path

from termcolor import colored
from typing_extensions import override

from mentat.code_file_manager import CodeFileManager
from mentat.parsers.change_display_helper import (
    DisplayInformation,
    FileActionType,
    get_file_action_type,
)
from mentat.parsers.diff_utils import matching_index
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.parser import Parser
from mentat.prompts.prompts import read_prompt

split_diff_parser_prompt_filename = Path("split_diff_parser_prompt.txt")


class SplitDiffDelimiters(Enum):
    FenceStart = "{fence[0]}"
    Start = "<<<<<<< HEAD"
    Middle = "======="
    End = ">>>>>>> updated"
    FenceEnd = "{fence[1]}"


class SplitDiffParser(Parser):
    @override
    def get_system_prompt(self) -> str:
        return read_prompt(split_diff_parser_prompt_filename)

    @override
    def provide_line_numbers(self) -> bool:
        return False

    @override
    def _code_line_beginning(
        self, display_information: DisplayInformation, cur_block: str
    ) -> str:
        lines = cur_block.split("\n")
        if SplitDiffDelimiters.Middle.value in lines:
            # Since we can't print surrounding lines for this parser,
            # no need for line_number_buffer - 1 spaces
            return colored("+", color="green")
        else:
            return colored("-", color="red")

    @override
    def _code_line_content(
        self,
        display_information: DisplayInformation,
        content: str,
        cur_line: str,
        cur_block: str,
    ) -> str:
        lines = cur_block.split("\n")
        if SplitDiffDelimiters.Middle.value in lines:
            return colored(content, color="green")
        else:
            return colored(content, color="red")

    @override
    def _could_be_special(self, cur_line: str) -> bool:
        line = cur_line.strip()
        # This stops us from printing the >>>>>> ====== and <<<<<< lines
        return any(
            delimiter.value.startswith(line) or line.startswith(delimiter.value)
            for delimiter in SplitDiffDelimiters
        )

    @override
    def _starts_special(self, line: str) -> bool:
        return line.strip().startswith(SplitDiffDelimiters.FenceStart.value)

    @override
    def _ends_special(self, line: str) -> bool:
        return line.strip().startswith(SplitDiffDelimiters.FenceStart.value)

    @override
    def _special_block(
        self,
        code_file_manager: CodeFileManager,
        git_root: Path,
        rename_map: dict[Path, Path],
        special_block: str,
    ) -> tuple[DisplayInformation, FileEdit, bool]:
        info = " ".join(special_block.strip().split(" ")[1:])
        is_creation = info.endswith(" +")
        is_deletion = info.endswith(" -")
        if is_creation or is_deletion:
            info = info[:-2]
        if " -> " in info:
            file_name, new_name = map(Path, info.split(" -> "))
        else:
            file_name, new_name = Path(info), None

        file_lines = self._get_file_lines(code_file_manager, rename_map, file_name)
        file_action_type = get_file_action_type(is_creation, is_deletion, new_name)
        display_information = DisplayInformation(
            file_name=file_name,
            file_lines=file_lines,
            added_block=[],
            removed_block=[],
            file_action_type=file_action_type,
            # Since we don't know where we're replacing until after the model outputs the removal block,
            # there's no way to print the surrounding lines
            first_changed_line=-1,
            last_changed_line=-1,
            new_name=new_name,
        )
        file_edit = FileEdit(
            git_root / file_name, [], is_creation, is_deletion, new_name
        )
        return (
            display_information,
            file_edit,
            file_action_type == FileActionType.UpdateFile,
        )

    @override
    def _ends_code(self, line: str) -> bool:
        return line.strip().startswith(SplitDiffDelimiters.FenceEnd.value)

    @override
    def _add_code_block(
        self,
        code_file_manager: CodeFileManager,
        rename_map: dict[Path, Path],
        special_block: str,
        code_block: str,
        display_information: DisplayInformation,
        file_edit: FileEdit,
    ) -> str:
        # Find matching set of lines; first we check for a direct match,
        # then we check for a match excluding case, then we check for a match
        # excluding case and stripped. If we don't find one, we throw away this change.
        file_lines = self._get_file_lines(
            code_file_manager, rename_map, display_information.file_name
        )
        # Remove the delimiters, ending fence, and new line after ending fence
        lines = code_block.split("\n")[1:-3]
        middle_index = lines.index(SplitDiffDelimiters.Middle.value)
        removed_lines = lines[:middle_index]
        added_lines = lines[middle_index + 1 :]
        index = matching_index(file_lines, removed_lines)
        if index == -1:
            return colored(
                "Error: Original lines not found. Discarding this change.",
                color="red",
            )
        file_edit.replacements.append(
            Replacement(index, index + len(removed_lines), added_lines)
        )
        return ""
