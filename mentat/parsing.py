import asyncio
import json
import logging
from enum import Enum
from json import JSONDecodeError
from pathlib import Path
from timeit import default_timer
from typing import Any, AsyncGenerator

import attr
from openai.error import InvalidRequestError, RateLimitError
from termcolor import cprint

from .code_change import CodeChange, CodeChangeAction
from .code_change_display import (
    change_delimiter,
    get_file_name,
    get_later_lines,
    get_previous_lines,
    get_removed_block,
)
from .code_file_manager import CodeFileManager
from .errors import MentatError, ModelError, UserError
from .llm_api import call_llm_api
from .streaming_printer import StreamingPrinter


class _BlockIndicator(Enum):
    Start = "@@start"
    Code = "@@code"
    End = "@@end"


@attr.s
class ParsingState:
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
    rename_map: dict[Path, Path] = attr.ib(factory=dict)

    def parse_line_printing(self, content: str):
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
        try:
            json_data = json.loads("\n".join(self.json_lines))
        except JSONDecodeError:
            raise ModelError(
                "Model gave malformed JSON for change",
                already_added_to_changelist=False,
            )

        new_change = CodeChange(
            json_data, self.code_lines, code_file_manager, self.rename_map
        )
        self.code_changes.append(new_change)
        self.json_lines, self.code_lines = [], []
        if new_change.action == CodeChangeAction.RenameFile:
            # This rename_map is a bit hacky; it shouldn't be used outside of streaming/parsing
            self.rename_map[new_change.name] = new_change.file

    def new_line(self, code_file_manager: CodeFileManager):
        to_print = ""
        entered_code_lines = False
        exited_code_lines = False
        created_code_change = False
        match self.cur_line.rstrip("\n"):
            case _BlockIndicator.Start.value:
                if self.in_special_lines or self.in_code_lines:
                    raise ModelError(
                        "Model gave start indicator while making change",
                        already_added_to_changelist=True,
                    )
                self.in_special_lines = True
            case _BlockIndicator.Code.value:
                if not self.in_special_lines:
                    raise ModelError(
                        "Model gave code indicator while it was not making a change",
                        already_added_to_changelist=False,
                    )
                if self.in_code_lines:
                    raise ModelError(
                        "Model gave code indicator while in code block",
                        already_added_to_changelist=True,
                    )
                self.in_code_lines = True
                self.create_code_change(code_file_manager)
                if not self.code_changes[-1].action.has_additions():
                    raise ModelError(
                        "Model gave code indicator for action without code",
                        already_added_to_changelist=True,
                    )
                entered_code_lines = True
                created_code_change = True
            case _BlockIndicator.End.value:
                if not self.in_special_lines:
                    raise ModelError(
                        "Model gave end indicator while not creating change",
                        already_added_to_changelist=False,
                    )
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
    state: ParsingState = ParsingState()
    start_time = default_timer()
    try:
        asyncio.run(
            stream_and_parse_llm_response(messages, model, state, code_file_manager)
        )
    except InvalidRequestError as e:
        raise MentatError(
            "Something went wrong - invalid request to OpenAI API. OpenAI returned:\n"
            + str(e)
        )
    except RateLimitError as e:
        raise UserError("OpenAI gave a rate limit error:\n" + str(e))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Using the response up to this point.")
        # if the last change is incomplete, remove it
        if state.in_code_lines:
            state.code_changes = state.code_changes[:-1]
        logging.info("User interrupted response.")

    state.code_changes = list(
        filter(lambda change: not change.error, state.code_changes)
    )

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
    try:
        await _process_response(state, response, printer, code_file_manager)
        printer.wrap_it_up()
        await printer_task
    except ModelError as e:
        logging.info(f"Model created error {e}")
        printer.wrap_it_up()
        # make sure we finish printing everything model sent before we encountered the crash
        await printer_task
        cprint("\n\nFatal error while processing model response:", "red")
        cprint(str(e), color="red")
        cprint("Using response up to this point.")
        if e.already_added_to_changelist:
            state.code_changes = state.code_changes[:-1]
    finally:
        logging.debug(f"LLM response:\n{state.message}")


async def _process_response(
    state: ParsingState,
    response: AsyncGenerator[Any, None],
    printer: StreamingPrinter,
    code_file_manager: CodeFileManager,
):
    def chunk_to_lines(chunk: Any) -> list[str]:
        return chunk["choices"][0]["delta"].get("content", "").splitlines(keepends=True)

    async for chunk in response:
        for content_line in chunk_to_lines(chunk):
            if content_line:
                state.message += content_line
                _process_content_line(state, content_line, printer, code_file_manager)

    # This newline solves at least 5 edge cases singlehandedly
    _process_content_line(state, "\n", printer, code_file_manager)

    # If the model forgot an @@end at the very end of it's message, we might as well add the change
    if state.in_special_lines:
        logging.info("Model forgot an @@end!")
        _process_content_line(state, "@@end\n", printer, code_file_manager)


def _process_content_line(
    state: ParsingState,
    content: str,
    printer: StreamingPrinter,
    code_file_manager: CodeFileManager,
):
    beginning = state.cur_line == ""
    state.cur_line += content

    if (
        state.in_code_lines and not state.code_changes[-1].error
    ) or not state.in_special_lines:
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
        (
            to_print,
            entered_code_lines,  # pyright: ignore[reportUnusedVariable]
            exited_code_lines,
            created_code_change,
        ) = state.new_line(code_file_manager)

        if created_code_change:
            cur_change = state.code_changes[-1]
            if cur_change.error:
                logging.info(
                    f"Model error when creating code change: {cur_change.error}"
                )
                printer.add_string("\nNot showing skipped change due to error:")
                printer.add_string(cur_change.error, color="red")
                printer.add_string(
                    "Continuing model response...\n", color="light_green"
                )
            else:
                if (
                    len(state.code_changes) < 2
                    or state.code_changes[-2].file != cur_change.file
                    or state.explained_since_change
                    or state.code_changes[-1].action == CodeChangeAction.RenameFile
                ):
                    printer.add_string(get_file_name(cur_change))
                    if (
                        cur_change.action.has_additions()
                        or cur_change.action.has_removals()
                    ):
                        printer.add_string(change_delimiter)
                state.explained_since_change = False
                printer.add_string(get_previous_lines(cur_change))
                printer.add_string(get_removed_block(cur_change))
                if (
                    not cur_change.action.has_additions()
                    and cur_change.action.has_removals()
                ):
                    printer.add_string(get_later_lines(cur_change))
                    printer.add_string(change_delimiter)

        if to_print and not (state.in_code_lines and state.code_changes[-1].error):
            prefix = (
                "+" + " " * (state.code_changes[-1].line_number_buffer - 1)
                if state.in_code_lines and beginning
                else ""
            )
            color = "green" if state.in_code_lines else None
            printer.add_string(prefix + to_print, end="", color=color)
        if exited_code_lines and not state.code_changes[-1].error:
            printer.add_string(get_later_lines(state.code_changes[-1]))
            printer.add_string(change_delimiter)
