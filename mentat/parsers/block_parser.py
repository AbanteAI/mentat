import json
from enum import Enum
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from typing_extensions import override

from mentat.code_file_manager import CodeFileManager
from mentat.errors import ModelError
from mentat.parsers.change_display_helper import DisplayInformation, FileActionType
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.parser import ParsedLLMResponse, Parser
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT

block_parser_prompt_filename = Path("block_parser_prompt.txt")


class _BlockParserAction(Enum):
    Insert = "insert"
    Replace = "replace"
    Delete = "delete"
    CreateFile = "create-file"
    DeleteFile = "delete-file"
    RenameFile = "rename-file"


class _BlockParserIndicator(Enum):
    Start = "@@start"
    Code = "@@code"
    End = "@@end"


class _BlockParserJsonKeys(Enum):
    File = "file"
    Action = "action"
    Name = "name"
    BeforeLine = "insert-before-line"
    AfterLine = "insert-after-line"
    StartLine = "start-line"
    EndLine = "end-line"


class _BlockParserDeserializedJson:
    def __init__(self, json_data: dict[str, Any]):
        self.file = json_data.get(_BlockParserJsonKeys.File.value, None)
        self.action = json_data.get(_BlockParserJsonKeys.Action.value, None)
        self.name = json_data.get(_BlockParserJsonKeys.Name.value, None)
        self.before_line = json_data.get(_BlockParserJsonKeys.BeforeLine.value, None)
        self.after_line = json_data.get(_BlockParserJsonKeys.AfterLine.value, None)
        self.start_line = json_data.get(_BlockParserJsonKeys.StartLine.value, None)
        self.end_line = json_data.get(_BlockParserJsonKeys.EndLine.value, None)

        if self.file is not None:
            self.file = Path(self.file)
        if self.action is not None:
            self.action: _BlockParserAction | None = _BlockParserAction(self.action)
        if self.name is not None:
            self.name = Path(self.name)
        if self.before_line is not None:
            self.before_line = int(self.before_line)
        if self.after_line is not None:
            self.after_line = int(self.after_line)
        if self.start_line is not None:
            self.start_line = int(self.start_line)
        if self.end_line is not None:
            self.end_line = int(self.end_line)


class BlockParser(Parser):
    @override
    def get_system_prompt(self) -> str:
        return read_prompt(block_parser_prompt_filename)

    @override
    def _could_be_special(self, cur_line: str) -> bool:
        return any(
            to_match.value.startswith(cur_line.strip())
            for to_match in _BlockParserIndicator
        ) and (bool(cur_line.strip()) or not cur_line.endswith("\n"))

    @override
    def _starts_special(self, line: str) -> bool:
        return line == _BlockParserIndicator.Start.value

    @override
    def _ends_special(self, line: str) -> bool:
        return (
            line == _BlockParserIndicator.Code.value
            or line == _BlockParserIndicator.End.value
        )

    @override
    def _special_block(
        self,
        code_file_manager: CodeFileManager,
        cwd: Path,
        rename_map: dict[Path, Path],
        special_block: str,
    ) -> tuple[DisplayInformation, FileEdit, bool]:
        block = special_block.strip().split("\n")
        json_lines = block[1:-1]
        try:
            json_data: dict[str, Any] = json.loads("\n".join(json_lines))
            deserialized_json = _BlockParserDeserializedJson(json_data)
        except (JSONDecodeError, ValueError):
            raise ModelError("Error: Model output malformed json.")

        if deserialized_json.action is None:
            raise ModelError("Error: Model output malformed json.")

        starting_line = 0
        ending_line = 0
        match deserialized_json.action:
            case _BlockParserAction.Insert:
                if deserialized_json.before_line is not None:
                    starting_line = deserialized_json.before_line - 1
                    if (
                        deserialized_json.after_line is not None
                        and starting_line != deserialized_json.after_line
                    ):
                        raise ModelError("Error: Model output malformed edit.")
                elif deserialized_json.after_line is not None:
                    starting_line = deserialized_json.after_line
                else:
                    raise ModelError("Error: Model output malformed edit.")
                ending_line = starting_line
                file_action = FileActionType.UpdateFile

            case _BlockParserAction.Replace | _BlockParserAction.Delete:
                if (
                    deserialized_json.start_line is None
                    or deserialized_json.end_line is None
                ):
                    raise ModelError("Error: Model output malformed edit.")
                starting_line = deserialized_json.start_line - 1
                ending_line = deserialized_json.end_line
                file_action = FileActionType.UpdateFile

            case _BlockParserAction.CreateFile:
                file_action = FileActionType.CreateFile

            case _BlockParserAction.DeleteFile:
                file_action = FileActionType.DeleteFile

            case _BlockParserAction.RenameFile:
                file_action = FileActionType.RenameFile
        if ending_line < starting_line:
            raise ModelError("Error: Model output malformed edit.")

        full_path = (cwd / deserialized_json.file).resolve()
        rename_file_path = (
            (cwd / deserialized_json.name).resolve() if deserialized_json.name else None
        )

        file_lines = self._get_file_lines(code_file_manager, rename_map, full_path)
        display_information = DisplayInformation(
            deserialized_json.file,
            file_lines,
            [],
            file_lines[starting_line:ending_line],
            file_action,
            starting_line,
            ending_line,
            deserialized_json.name,
        )

        replacements = list[Replacement]()
        if deserialized_json.action == _BlockParserAction.Delete:
            replacements.append(Replacement(starting_line, ending_line, []))
        file_edit = FileEdit(
            full_path,
            replacements,
            is_creation=file_action == FileActionType.CreateFile,
            is_deletion=file_action == FileActionType.DeleteFile,
            rename_file_path=rename_file_path,
        )
        has_code = block[-1] == _BlockParserIndicator.Code.value
        return (display_information, file_edit, has_code)

    @override
    def _ends_code(self, line: str) -> bool:
        return line == _BlockParserIndicator.End.value

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

    def file_edits_to_llm_message(self, parsedLLMResponse: ParsedLLMResponse) -> str:
        """
        Inverse of stream_and_parse_llm_response
        """
        session_context = SESSION_CONTEXT.get()

        ans = parsedLLMResponse.conversation.strip() + "\n\n"
        for file_edit in parsedLLMResponse.file_edits:
            tmp = {}
            tmp[_BlockParserJsonKeys.File.value] = file_edit.file_path.relative_to(
                session_context.cwd
            ).as_posix()
            if file_edit.is_creation:
                tmp[_BlockParserJsonKeys.Action.value] = (
                    _BlockParserAction.CreateFile.value
                )
            elif file_edit.is_deletion:
                tmp[_BlockParserJsonKeys.Action.value] = (
                    _BlockParserAction.DeleteFile.value
                )
            elif file_edit.rename_file_path is not None:
                tmp[_BlockParserJsonKeys.Action.value] = (
                    _BlockParserAction.RenameFile.value
                )
                tmp[_BlockParserJsonKeys.Name.value] = (
                    file_edit.rename_file_path.relative_to(
                        session_context.cwd
                    ).as_posix()
                )
            if _BlockParserJsonKeys.Action.value in tmp:
                ans += _BlockParserIndicator.Start.value + "\n"
                ans += json.dumps(tmp, indent=4) + "\n"
                if (
                    tmp[_BlockParserJsonKeys.Action.value]
                    == _BlockParserAction.CreateFile.value
                ):
                    ans += _BlockParserIndicator.Code.value + "\n"
                    ans += "\n".join(file_edit.replacements[0].new_lines) + "\n"
                ans += _BlockParserIndicator.End.value + "\n"
            if not file_edit.is_creation:
                for replacement in file_edit.replacements:
                    tmp = {}
                    tmp[_BlockParserJsonKeys.File.value] = (
                        file_edit.file_path.relative_to(session_context.cwd).as_posix()
                    )
                    ans += _BlockParserIndicator.Start.value + "\n"
                    starting_line = replacement.starting_line
                    ending_line = replacement.ending_line
                    if len(replacement.new_lines) == 0:
                        tmp[_BlockParserJsonKeys.Action.value] = (
                            _BlockParserAction.Delete.value
                        )
                        tmp[_BlockParserJsonKeys.StartLine.value] = starting_line + 1
                        tmp[_BlockParserJsonKeys.EndLine.value] = ending_line
                    else:
                        if starting_line == ending_line:
                            tmp[_BlockParserJsonKeys.Action.value] = (
                                _BlockParserAction.Insert.value
                            )
                            tmp[_BlockParserJsonKeys.AfterLine.value] = starting_line
                            tmp[_BlockParserJsonKeys.BeforeLine.value] = ending_line + 1
                        else:
                            tmp[_BlockParserJsonKeys.Action.value] = (
                                _BlockParserAction.Replace.value
                            )
                            tmp[_BlockParserJsonKeys.StartLine.value] = (
                                starting_line + 1
                            )
                            tmp[_BlockParserJsonKeys.EndLine.value] = ending_line
                    ans += json.dumps(tmp, indent=4) + "\n"
                    if len(replacement.new_lines) > 0:
                        ans += _BlockParserIndicator.Code.value + "\n"
                        ans += "\n".join(replacement.new_lines) + "\n"
                    ans += _BlockParserIndicator.End.value + "\n"

        return ans
