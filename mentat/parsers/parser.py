from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import Event
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import attr
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.completion_create_params import ResponseFormat
from termcolor import colored

from mentat.code_file_manager import CodeFileManager
from mentat.errors import ModelError
from mentat.llm_api_handler import chunk_to_lines
from mentat.parsers.change_display_helper import (
    DisplayInformation,
    FileActionType,
    change_delimiter,
    get_file_name,
    get_later_lines,
    get_previous_lines,
    get_removed_lines,
)
from mentat.parsers.file_edit import FileEdit
from mentat.session_context import SESSION_CONTEXT
from mentat.streaming_printer import StreamingPrinter
from mentat.utils import convert_string_to_asynciter


@attr.define
class ParsedLLMResponse:
    full_response: str = attr.field()
    conversation: str = attr.field()
    file_edits: list[FileEdit] = attr.field()
    interrupted: bool = attr.field(default=False)


class Parser(ABC):
    def __init__(self):
        self.shutdown = Event()
        self._interrupt_task = None
        self._silence_printer = False

    async def listen_for_interrupt(self):
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        async with stream.interrupt_lock:
            await stream.recv("interrupt")
            logging.info("User interrupted response.")
            self.shutdown.set()

    @asynccontextmanager
    async def interrupt_catcher(self):
        self._interrupt_task = asyncio.create_task(self.listen_for_interrupt())
        yield
        if self._interrupt_task is not None:  # type: ignore
            self._interrupt_task.cancel()
            try:
                await self._interrupt_task
            except asyncio.CancelledError:
                pass
        self._interrupt_task = None
        self.shutdown.clear()

    @abstractmethod
    def get_system_prompt(self) -> str:
        pass

    def response_format(self) -> ResponseFormat:
        return ResponseFormat(type="text")

    async def stream_and_parse_llm_response(
        self, response: AsyncIterator[ChatCompletionChunk]
    ) -> ParsedLLMResponse:
        """
        This general parsing structure relies on the assumption that all formats require three types of lines:
        1. 'conversation' lines, which are streamed as they come,
        2. 'special' lines, that are never shown to the user and contain information such as the file_name
        3. 'code' lines, which are the actual code written and are shown to the user in a special format
        To make a parser that differs from these assumptions, override this method instead of the helper methods
        """
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_file_manager = session_context.code_file_manager

        printer = StreamingPrinter()
        if self._silence_printer:
            printer_task = None
        else:
            printer_task = asyncio.create_task(printer.print_lines())
        message = ""
        conversation = ""
        file_edits = dict[Path, FileEdit]()

        cur_line = ""
        prev_block = ""
        cur_block = ""
        display_information: DisplayInformation | None = None
        file_edit: FileEdit | None = None
        line_printed = False
        in_special_lines = False
        in_code_lines = False
        in_conversation = True
        printed_delimiter = False
        rename_map = dict[Path, Path]()
        interrupted = False
        async for chunk in response:
            if self.shutdown.is_set():
                interrupted = True
                printer.shutdown_printer()
                if printer_task is not None:
                    await printer_task
                stream.send(
                    colored("")  # Reset ANSI codes
                    + "\n\nInterrupted by user. Using the response up to this point."
                )
                break

            for content in chunk_to_lines(chunk):
                if not content:
                    continue
                message += content
                cur_line += content

                # Print if not in special lines and line is confirmed not special
                if not in_special_lines:
                    if not line_printed:
                        if not self._could_be_special(cur_line):
                            line_printed = True
                            to_print = (
                                cur_line
                                if not in_code_lines or display_information is None
                                else self._code_line_beginning(
                                    display_information, cur_block
                                )
                                + self._code_line_content(
                                    display_information, cur_line, cur_line, cur_block
                                )
                            )
                            printer.add_string(to_print, end="")
                            if not in_code_lines or display_information is None:
                                conversation += to_print
                    else:
                        to_print = (
                            content
                            if not in_code_lines or display_information is None
                            else self._code_line_content(
                                display_information, content, cur_line, cur_block
                            )
                        )
                        printer.add_string(to_print, end="")
                        if not in_code_lines or display_information is None:
                            conversation += to_print

                # If we print non code lines, we want to reprint the file name of the next change,
                # even if it's the same file as the last change
                if not in_code_lines and not in_special_lines and line_printed:
                    in_conversation = True

                # New line handling
                if "\n" in cur_line:
                    # Now that full line is in, give _could_be_special full line (including newline)
                    # and see if it should be printed or not
                    if (
                        not in_special_lines
                        and not line_printed
                        and not self._could_be_special(cur_line)
                    ):
                        to_print = (
                            cur_line
                            if not in_code_lines or display_information is None
                            else self._code_line_beginning(
                                display_information, cur_block
                            )
                            + self._code_line_content(
                                display_information, cur_line, cur_line, cur_block
                            )
                        )
                        printer.add_string(to_print, end="")
                        line_printed = True

                    if self._starts_special(cur_line.strip()):
                        in_special_lines = True

                    if in_special_lines or in_code_lines:
                        cur_block += cur_line

                    if in_special_lines and self._ends_special(cur_line.strip()):
                        previous_file = (
                            None if file_edit is None else file_edit.file_path
                        )

                        try:
                            (
                                display_information,
                                file_edit,
                                in_code_lines,
                            ) = self._special_block(
                                code_file_manager,
                                session_context.cwd,
                                rename_map,
                                cur_block,
                            )
                        except ModelError as e:
                            printer.add_string(str(e), color="red")
                            printer.add_string("Using existing changes.")
                            printer.wrap_it_up()
                            if printer_task is not None:
                                await printer_task
                            logging.debug("LLM Response:")
                            logging.debug(message)
                            return ParsedLLMResponse(
                                message,
                                conversation,
                                [file_edit for file_edit in file_edits.values()],
                            )

                        in_special_lines = False
                        prev_block = cur_block
                        cur_block = ""

                        # Rename map handling
                        if file_edit.rename_file_path is not None:
                            rename_map[file_edit.rename_file_path] = file_edit.file_path
                        if file_edit.file_path in rename_map:
                            file_edit.file_path = (
                                session_context.cwd / rename_map[file_edit.file_path]
                            )

                        # New file_edit creation and merging
                        if file_edit.file_path not in file_edits:
                            file_edits[file_edit.file_path] = file_edit
                        else:
                            cur_file_edit = file_edits[file_edit.file_path]
                            cur_file_edit.is_creation = (
                                cur_file_edit.is_creation or file_edit.is_creation
                            )
                            cur_file_edit.is_deletion = (
                                cur_file_edit.is_deletion or file_edit.is_deletion
                            )
                            if file_edit.rename_file_path is not None:
                                cur_file_edit.rename_file_path = (
                                    file_edit.rename_file_path
                                )
                            cur_file_edit.replacements.extend(file_edit.replacements)
                            file_edit = cur_file_edit

                        # Print file header
                        if (
                            in_conversation
                            or display_information.file_action_type
                            == FileActionType.RenameFile
                            or (file_edit.file_path != previous_file)
                        ):
                            in_conversation = False
                            printer.add_string(get_file_name(display_information))
                            if in_code_lines or display_information.removed_block:
                                printed_delimiter = True
                                printer.add_string(change_delimiter)
                            else:
                                printed_delimiter = False
                        elif not printed_delimiter:
                            # We have to have this so that putting a change like an insert after a rename
                            # still has a change delimiter
                            printer.add_string(change_delimiter)
                            printed_delimiter = True

                        # Print previous lines, removed block, and possibly later lines
                        if in_code_lines or display_information.removed_block:
                            printer.add_string(get_previous_lines(display_information))
                            printer.add_string(get_removed_lines(display_information))
                            if not in_code_lines:
                                printer.add_string(get_later_lines(display_information))
                                printer.add_string(change_delimiter)
                    elif in_code_lines and self._ends_code(cur_line.strip()):
                        # Adding code lines to previous file_edit and printing later lines
                        if display_information is not None and file_edit is not None:
                            to_display = self._add_code_block(
                                code_file_manager,
                                rename_map,
                                prev_block,
                                cur_block,
                                display_information,
                                file_edit,
                            )
                            printer.add_string(get_later_lines(display_information))
                            printer.add_string(change_delimiter)
                            printer.add_string(to_display)
                        else:
                            printer.add_string(change_delimiter)

                        in_code_lines = False
                        prev_block = cur_block
                        cur_block = ""
                    line_printed = False
                    cur_line = ""
        else:
            # If the model doesn't close out the code lines, we might as well do it for it
            if (
                in_code_lines
                and display_information is not None
                and file_edit is not None
            ):
                to_display = self._add_code_block(
                    code_file_manager,
                    rename_map,
                    prev_block,
                    cur_block,
                    display_information,
                    file_edit,
                )
                printer.add_string(get_later_lines(display_information))
                printer.add_string(change_delimiter)
                printer.add_string(to_display)

            # Only finish printing if we don't quit from ctrl-c
            printer.wrap_it_up()
            if printer_task is not None:
                await printer_task

        logging.debug("LLM Response:")
        logging.debug(message)
        return ParsedLLMResponse(
            message,
            conversation,
            [file_edit for file_edit in file_edits.values()],
            interrupted,
        )

    # Ideally this would be called in this class instead of subclasses
    def _get_file_lines(
        self,
        code_file_manager: CodeFileManager,
        rename_map: dict[Path, Path],
        abs_path: Path,
    ) -> list[str]:
        path = rename_map.get(
            abs_path,
            abs_path,
        )
        return code_file_manager.file_lines.get(path, [])

    # These methods aren't abstract, since most parsers will use this implementation, but can be overriden easily
    def provide_line_numbers(self) -> bool:
        return True

    def line_number_starting_index(self) -> int:
        return 1

    def _code_line_beginning(
        self, display_information: DisplayInformation, cur_block: str
    ) -> str:
        """
        The beginning of a code line; normally this means printing the + prefix
        """
        return colored(
            "+" + " " * (display_information.line_number_buffer - 1), color="green"
        )

    def _code_line_content(
        self,
        display_information: DisplayInformation,
        content: str,
        cur_line: str,
        cur_block: str,
    ) -> str:
        """
        Part of a code line; normally this means printing in green
        """
        return colored(content, color="green")

    # These methods must be overriden if using the default stream and parse function
    def _could_be_special(self, cur_line: str) -> bool:
        """
        Returns if this current line could be a special line and therefore shouldn't be printed yet.
        Once line is completed, will include a newline character.
        """
        raise NotImplementedError()

    def _starts_special(self, line: str) -> bool:
        """
        Determines if this line begins a special block
        """
        raise NotImplementedError()

    def _ends_special(self, line: str) -> bool:
        """
        Determines if this line ends a special block
        """
        raise NotImplementedError()

    def _special_block(
        self,
        code_file_manager: CodeFileManager,
        cwd: Path,
        rename_map: dict[Path, Path],
        special_block: str,
    ) -> tuple[DisplayInformation, FileEdit, bool]:
        """
        After finishing special block, return DisplayInformation to print, FileEdit to add/merge to list,
        and if a code block follows this special block.
        """
        raise NotImplementedError()

    def _ends_code(self, line: str) -> bool:
        """
        Determines if this line ends a code block
        """
        raise NotImplementedError()

    def _add_code_block(
        self,
        code_file_manager: CodeFileManager,
        rename_map: dict[Path, Path],
        special_block: str,
        code_block: str,
        display_information: DisplayInformation,
        file_edit: FileEdit,
    ) -> str:
        """
        Using the special block, code block and display_information, edits the FileEdit to add the new code block.
        Can return a message to print after this change is finished.
        """
        raise NotImplementedError()

    async def parse_llm_response(self, response: str) -> ParsedLLMResponse:
        self._silence_printer = True
        async_iter_response = convert_string_to_asynciter(response, chunk_size=100)
        parsed_response = await self.stream_and_parse_llm_response(async_iter_response)
        self._silence_printer = False
        return parsed_response
