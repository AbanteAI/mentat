import asyncio
import json
import logging
from enum import Enum
from timeit import default_timer
from typing import Generator

import attr
import openai
from termcolor import cprint

from .code_change import CodeChange
from .code_change_display import (
    change_delimiter,
    get_file_name,
    get_later_lines,
    get_previous_lines,
    get_removed_block,
)
from .code_file_manager import CodeFileManager
from .llm_api import call_llm_api
from .streaming_printer import StreamingPrinter


class _BlockIndicator(Enum):
    Start = "@@start"
    Code = "@@code"
    End = "@@end"


@attr.s
class ParsingState:
    git_root: str = attr.ib(init=True)
    message: str = attr.ib(default="")
    cur_line: str = attr.ib(default="")
    cur_printed: bool = attr.ib(default=False)
    time_elapsed: float = attr.ib(default=0)
    in_special_lines: bool = attr.ib(default=False)
    in_code_lines: bool = attr.ib(default=False)
    explanation: str = attr.ib(default="")
    explained_since_change: bool = attr.ib(default=True)
    code_changes: list[CodeChange] = attr.ib(factory=list)
    json_lines: list[str] = attr.ib(factory=list)
    code_lines: list[str] = attr.ib(factory=list)

    def parse_line_printing(self, content):
        to_print = ""
        if self.cur_printed:
            to_print = content
        elif not self.could_be_special():
            to_print = self.cur_line
            self.cur_printed = True

        if not self.in_special_lines:
            self.explanation += to_print
            if to_print:
                self.explained_since_change = True

        return to_print

    def could_be_special(self):
        return any(
            len(self.cur_line.rstrip("\n")) <= len(to_match.value)
            and to_match.value.startswith(self.cur_line.rstrip("\n"))
            for to_match in _BlockIndicator
        )

    def create_code_change(self, code_file_manager: CodeFileManager):
        json_data = json.loads("\n".join(self.json_lines))
        self.code_changes.append(
            CodeChange(json_data, self.code_lines, self.git_root, code_file_manager)
        )
        self.json_lines, self.code_lines = [], []

    def new_line(self, code_file_manager: CodeFileManager):
        to_print = ""
        entered_code_lines = False
        exited_code_lines = False
        created_code_change = False
        match self.cur_line.rstrip("\n"):
            case _BlockIndicator.Start.value:
                assert not self.in_special_lines and not self.in_code_lines
                self.in_special_lines = True
            case _BlockIndicator.Code.value:
                assert self.in_special_lines and not self.in_code_lines
                self.in_code_lines = True
                self.create_code_change(code_file_manager)
                entered_code_lines = True
                created_code_change = True
            case _BlockIndicator.End.value:
                assert self.in_special_lines
                if not self.in_code_lines:
                    self.create_code_change(code_file_manager)
                    created_code_change = True
                else:
                    self.code_changes[-1].code_lines = self.code_lines
                    self.code_lines = []
                    exited_code_lines = True
                self.in_special_lines, self.in_code_lines = False, False
            case _:
                if self.in_code_lines:
                    self.code_lines.append(self.cur_line.rstrip("\n"))
                elif self.in_special_lines:
                    self.json_lines.append(self.cur_line)
                elif not self.cur_printed:
                    self.explanation += self.cur_line
                    if self.cur_line:
                        self.explained_since_change = True

                if not self.cur_printed and (
                    self.in_code_lines or not self.in_special_lines
                ):
                    # Lets us print lines that start with @@start
                    to_print = self.cur_line

        self.cur_line = ""
        self.cur_printed = False
        return to_print, entered_code_lines, exited_code_lines, created_code_change


def run_async_stream_and_parse_llm_response(
    messages: list[dict[str, str]],
    model: str,
    code_file_manager: CodeFileManager,
) -> ParsingState:
    state: ParsingState = ParsingState(git_root=code_file_manager.git_root)
    start_time = default_timer()
    try:
        asyncio.run(
            stream_and_parse_llm_response(messages, model, state, code_file_manager)
        )
    except openai.error.InvalidRequestError as e:
        cprint(e, "red")
        exit()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Using the response up to this point.")
        # if the last change is incomplete, remove it
        if state.in_code_lines:
            state.code_changes = state.code_changes[:-1]
        logging.info("User interrupted response.")

    state.time_elapsed = default_timer() - start_time
    return state


async def stream_and_parse_llm_response(
    messages: list[dict[str, str]],
    model: str,
    state: ParsingState,
    code_file_manager: CodeFileManager,
) -> None:
    response = await call_llm_api(messages, model)

    print("\nstreaming...  use control-c to interrupt the model at any point\n")

    printer = StreamingPrinter()
    printer_task = asyncio.create_task(printer.print_lines())
    await _process_response(state, response, printer, code_file_manager)
    printer.wrap_it_up()
    await printer_task

    logging.debug(f"LLM response:\n{state.message}")


async def _process_response(
    state: ParsingState,
    response: Generator,
    printer: StreamingPrinter,
    code_file_manager: CodeFileManager,
):
    def chunk_to_lines(chunk):
        return chunk["choices"][0]["delta"].get("content", "").splitlines(keepends=True)

    async for chunk in response:
        for content_line in chunk_to_lines(chunk):
            if content_line:
                state.message += content_line
                _process_content_line(state, content_line, printer, code_file_manager)
    _process_content_line(state, "\n", printer, code_file_manager)


def _process_content_line(
    state, content, printer: StreamingPrinter, code_file_manager: CodeFileManager
):
    beginning = state.cur_line == ""
    state.cur_line += content

    if state.in_code_lines or not state.in_special_lines:
        to_print = state.parse_line_printing(content)
        prefix = (
            "+" + " " * (state.code_changes[-1].line_number_buffer - 1)
            if state.in_code_lines and beginning
            else ""
        )
        color = "green" if state.in_code_lines else None
        if to_print:
            printer.add_string(prefix + to_print, end="", color=color)

    if "\n" in content:
        to_print, entered_code_lines, exited_code_lines, created_code_change = (
            state.new_line(code_file_manager)
        )

        if created_code_change:
            cur_change = state.code_changes[-1]
            if (
                len(state.code_changes) < 2
                or state.code_changes[-2].file != cur_change.file
                or state.explained_since_change
            ):
                printer.add_string(get_file_name(cur_change))
                printer.add_string(change_delimiter)
            state.explained_since_change = False
            printer.add_string(get_previous_lines(cur_change))
            printer.add_string(get_removed_block(cur_change))
            if not cur_change.action.has_additions():
                printer.add_string(get_later_lines(cur_change))
                printer.add_string(change_delimiter)

        prefix = (
            "+" + " " * (state.code_changes[-1].line_number_buffer - 1)
            if state.in_code_lines and beginning
            else ""
        )
        color = "green" if state.in_code_lines else None
        if to_print:
            printer.add_string(prefix + to_print, end="", color=color)
        if exited_code_lines:
            printer.add_string(get_later_lines(state.code_changes[-1]))
            printer.add_string(change_delimiter)
