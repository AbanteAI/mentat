from enum import Enum
from pathlib import Path

from typing_extensions import override

from mentat.code_file_manager import CodeFileManager
from mentat.parsers.change_display_helper import (
    DisplayInformation,
    get_file_action_type,
    highlight_text,
)
from mentat.parsers.diff_utils import matching_index
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.parser import Parser
from mentat.parsers.streaming_printer import FormattedString
from mentat.prompts.prompts import read_prompt

unified_diff_parser_prompt_filename = Path("unified_diff_parser_prompt.txt")


class UnifiedDiffDelimiter(Enum):
    SpecialStart = "---"
    SpecialEnd = "+++"
    MidChange = "@@ @@\n"
    EndChange = "@@ end @@\n"


class UnifiedDiffParser(Parser):
    @override
    def get_system_prompt(self) -> str:
        return read_prompt(unified_diff_parser_prompt_filename)

    @override
    def provide_line_numbers(self) -> bool:
        return False

    @override
    def _code_line_beginning(self, display_information: DisplayInformation, cur_block: str) -> FormattedString:
        return ("", {})

    @override
    def _code_line_content(
        self,
        display_information: DisplayInformation,
        content: str,
        cur_line: str,
        cur_block: str,
    ) -> FormattedString:
        if cur_line == UnifiedDiffDelimiter.MidChange.value:
            return [("", {"delimiter": True}), ("\n", {})]
        elif cur_line.startswith("+"):
            return (content, {"color": "green"})
        elif cur_line.startswith("-"):
            return (content, {"color": "red"})
        else:
            return highlight_text(content, display_information.lexer)

    @override
    def _could_be_special(self, cur_line: str) -> bool:
        return (
            # Since the model is printing the context lines, we can only
            # highlight them once we get a full line, so we choose to
            # add the lines to the printer all at once.
            not cur_line.endswith("\n")
            or UnifiedDiffDelimiter.EndChange.value.startswith(cur_line)
            or cur_line.startswith(UnifiedDiffDelimiter.SpecialStart.value)
            or cur_line.startswith(UnifiedDiffDelimiter.SpecialEnd.value)
            or UnifiedDiffDelimiter.SpecialStart.value.startswith(cur_line)
            or UnifiedDiffDelimiter.SpecialEnd.value.startswith(cur_line)
        )

    @override
    def _starts_special(self, line: str) -> bool:
        return line.startswith(UnifiedDiffDelimiter.SpecialStart.value)

    @override
    def _ends_special(self, line: str) -> bool:
        return line.startswith(UnifiedDiffDelimiter.MidChange.value.strip()) or line.startswith(
            UnifiedDiffDelimiter.EndChange.value.strip()
        )

    @override
    def _special_block(
        self,
        code_file_manager: CodeFileManager,
        cwd: Path,
        rename_map: dict[Path, Path],
        special_block: str,
    ) -> tuple[DisplayInformation, FileEdit, bool]:
        lines = special_block.strip().split("\n")
        file_name = lines[0][4:]
        new_name = lines[1][4:]
        is_creation = file_name == "/dev/null"
        is_deletion = new_name == "/dev/null"
        if is_creation:
            file_name = new_name
        if file_name == new_name or is_deletion:
            new_name = None
        else:
            new_name = Path(new_name)
        file_name = Path(file_name)
        full_path = (cwd / file_name).resolve()
        file_lines = self._get_file_lines(code_file_manager, rename_map, full_path)
        file_action_type = get_file_action_type(is_creation, is_deletion, new_name)
        display_information = DisplayInformation(file_name, file_lines, [], [], file_action_type, -1, -1, new_name)
        file_edit = FileEdit(
            full_path,
            [],
            is_creation,
            is_deletion,
            (cwd / new_name).resolve() if new_name else None,
        )
        return (
            display_information,
            file_edit,
            lines[-1].startswith(UnifiedDiffDelimiter.MidChange.value.strip()),
        )

    @override
    def _ends_code(self, line: str) -> bool:
        return line.strip() == UnifiedDiffDelimiter.EndChange.value.strip()

    @override
    def _add_code_block(
        self,
        code_file_manager: CodeFileManager,
        rename_map: dict[Path, Path],
        special_block: str,
        code_block: str,
        display_information: DisplayInformation,
        file_edit: FileEdit,
    ):
        file_lines = self._get_file_lines(code_file_manager, rename_map, file_edit.file_path).copy()

        # First, we split by the symbols that separate changes.
        lines = code_block.split("\n")
        changes = list[list[str]]()
        cur_lines = list[str]()
        for line in lines:
            if (
                line.strip() == UnifiedDiffDelimiter.MidChange.value.strip()
                or line.strip() == UnifiedDiffDelimiter.EndChange.value.strip()
            ):
                changes.append(cur_lines)
                cur_lines = list[str]()
                if line.strip() == UnifiedDiffDelimiter.EndChange.value.strip():
                    break
            else:
                if (
                    # Remove empty lines; hopefully the model always puts a space for context lines
                    line and not line.startswith("+") and not line.startswith("-") and not line.startswith(" ")
                ):
                    return
                cur_lines.append(line)
        if cur_lines:
            changes.append(cur_lines)

        # Next, we collect the - and context lines, search for their locations, and set the replacement ranges
        replacements = list[Replacement]()
        for change in changes:
            if not change:
                continue
            # We need both removals and context in this array this one
            search_lines = list[str]()
            for line in change:
                if line.startswith("-") or line.startswith(" "):
                    search_lines.append(line[1:])
            if not search_lines:
                # If the model gave us no context lines, we place at the start of the file;
                # this most commonly happens with imports
                replacements.append(Replacement(0, 0, [line[1:] for line in change]))
                continue

            start_index = matching_index(file_lines, search_lines)
            if start_index == -1:
                return

            # Matching lines checks for matches that are missing whitespace only lines;
            # this will cause errors with line numbering if we don't add those lines into the change lines
            cur_file_index = start_index
            cur_change_index = 0
            while cur_change_index < len(change) and cur_file_index < len(file_lines):
                cur_change_line = change[cur_change_index]
                if cur_change_line.startswith("+"):
                    cur_change_index += 1
                    continue
                cur_file_line = file_lines[cur_file_index]

                if not cur_file_line.strip() and cur_change_line.strip():
                    change.insert(cur_change_index, "")
                elif not cur_change_line.strip() and cur_file_line.strip():
                    file_lines.insert(cur_file_index, "")
                cur_file_index += 1
                cur_change_index += 1

            # We need a separate Replacement whenever context lines are between a group of additions/removals
            cur_start = None
            cur_additions = list[str]()
            cur_index = start_index
            for line in change:
                if line.startswith(" ") or not line:
                    if cur_start is not None:
                        replacements.append(Replacement(cur_start, cur_index, cur_additions))
                    cur_index += 1
                    cur_additions = list[str]()
                    cur_start = None
                elif line.startswith("+"):
                    if cur_start is None:
                        cur_start = cur_index
                    cur_additions.append(line[1:])
                elif line.startswith("-"):
                    if cur_start is None:
                        cur_start = cur_index
                    cur_index += 1
            if cur_start is not None:
                replacements.append(Replacement(cur_start, cur_index, cur_additions))

        file_edit.replacements.extend(replacements)
