from pathlib import Path

from typing_extensions import override

from mentat.code_file_manager import CodeFileManager
from mentat.errors import ModelError
from mentat.parsers.change_display_helper import DisplayInformation, FileActionType
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.parser import Parser
from mentat.prompts.prompts import read_prompt

replacement_parser_prompt_filename = Path("replacement_parser_prompt.txt")


class ReplacementParser(Parser):
    @override
    def get_system_prompt(self) -> str:
        return read_prompt(replacement_parser_prompt_filename)

    @override
    def _could_be_special(self, cur_line: str) -> bool:
        return cur_line.startswith("@")

    @override
    def _starts_special(self, line: str) -> bool:
        return line.startswith("@") and len(line.strip()) > 1

    @override
    def _ends_special(self, line: str) -> bool:
        return line.startswith("@")

    @override
    def _special_block(
        self,
        code_file_manager: CodeFileManager,
        git_root: Path,
        rename_map: dict[Path, Path],
        special_block: str,
    ) -> tuple[DisplayInformation, FileEdit, bool]:
        info = special_block.strip().split(" ")[1:]
        if len(info) == 0:
            raise ModelError("Error: Invalid model output")

        file_name = Path(info[0])
        file_lines = self._get_file_lines(code_file_manager, rename_map, file_name)
        new_name = None

        # For an insert, just make the second number 1 less than the starting line (since we sub 1 from starting line)
        if len(info) == 2 and info[1].startswith("insert_line="):
            info.append(f"ending_line={int(info[1].split('=')[1])-1}")

        if len(info) == 2:
            starting_line = 0
            ending_line = 0
            removed_lines = []
            match info[1]:
                case "+":
                    file_action_type = FileActionType.CreateFile
                case "-":
                    file_action_type = FileActionType.DeleteFile
                case _:
                    file_action_type = FileActionType.RenameFile
                    new_name = Path(info[1])
        elif len(info) == 3:
            try:
                # Convert from 1-index to 0-index
                starting_line = int(info[1].split("=")[1]) - 1
                # 1-index to 0-index = -1, inclusive to exclusive = +1
                ending_line = int(info[2].split("=")[1])
            except (ValueError, IndexError):
                raise ModelError("Error: Invalid line numbers given")
            if starting_line > ending_line or starting_line < 0 or ending_line < 0:
                raise ModelError("Error: Invalid line numbers given")
            removed_lines = file_lines[starting_line:ending_line]
            file_action_type = FileActionType.UpdateFile
        else:
            raise ModelError("Error: Invalid model output")

        display_information = DisplayInformation(
            file_name,
            file_lines,
            [],
            removed_lines,
            file_action_type,
            starting_line,
            ending_line,
            new_name=new_name,
        )

        file_edit = FileEdit(
            git_root / file_name,
            [],
            is_creation=file_action_type == FileActionType.CreateFile,
            is_deletion=file_action_type == FileActionType.DeleteFile,
            rename_file_path=new_name,
        )
        has_code = file_action_type == FileActionType.UpdateFile
        return (display_information, file_edit, has_code)

    @override
    def _ends_code(self, line: str) -> bool:
        return line.strip() == "@"

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
        file_edit.replacements.append(
            Replacement(
                display_information.first_changed_line,
                display_information.last_changed_line,
                code_block.split("\n")[:-2],
            )
        )
        return ""
