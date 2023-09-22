import asyncio
import json
import logging
from enum import Enum
from json import JSONDecodeError
from pathlib import Path
from timeit import default_timer
from typing import Generator

import attr
import openai
import openai.error
from ipdb import set_trace

from .code_change import CodeChange, CodeChangeAction
from .code_change_display import (
    change_delimiter,
    print_file_name,
    print_later_lines,
    print_previous_lines,
    print_removed_block,
)
from .code_file_manager import CodeFileManager
from .errors import MentatError, ModelError, RemoteKeyboardInterrupt, UserError
from .llm_api import call_llm_api
from .session_input import listen_for_interrupt
from .session_stream import get_session_stream


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


async def run_stream_and_parse_llm_response(
    messages: list[dict[str, str]],
    model: str,
    code_file_manager: CodeFileManager,
) -> ParsingState:
    stream = get_session_stream()

    state: ParsingState = ParsingState()
    start_time = default_timer()

    try:
        await listen_for_interrupt(
            stream_and_parse_llm_response(messages, model, state, code_file_manager)
        )
    except openai.error.InvalidRequestError as e:
        raise MentatError(
            "Something went wrong - invalid request to OpenAI API. OpenAI returned:\n"
            + str(e)
        )
    except openai.error.RateLimitError as e:
        raise UserError("OpenAI gave a rate limit error:\n" + str(e))
    except RemoteKeyboardInterrupt:
        await stream.send("Interrupted by user. Using the response up to this point.")
        # if the last change is incomplete, remove it
        if state.in_code_lines:
            state.code_changes = state.code_changes[:-1]
        logging.debug("User interrupted response.")

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
    stream = get_session_stream()

    response = await call_llm_api(messages, model)

    await stream.send("streaming...  use control-c to interrupt the model at any point")

    try:
        await _process_response(state, response, code_file_manager)
    except ModelError as e:
        logging.info(f"Model created error {e}")
        # make sure we finish printing everything model sent before we encountered the crash
        await stream.send(
            f"Fatal error while processing model response: {e}", color="red"
        )
        await stream.send("Using response up to this point.")
        if e.already_added_to_changelist:
            state.code_changes = state.code_changes[:-1]
    finally:
        logging.debug(f"LLM response:\n{state.message}")


async def _process_response(
    state: ParsingState,
    response: Generator,
    code_file_manager: CodeFileManager,
):
    def chunk_to_lines(chunk):
        return chunk["choices"][0]["delta"].get("content", "").splitlines(keepends=True)

    async for chunk in response:
        for content_line in chunk_to_lines(chunk):
            if content_line:
                state.message += content_line
                await _process_content_line(state, content_line, code_file_manager)

    # This newline solves at least 5 edge cases singlehandedly
    await _process_content_line(state, "\n", code_file_manager)

    # If the model forgot an @@end at the very end of it's message, we might as well add the change
    if state.in_special_lines:
        logging.info("Model forgot an @@end!")
        await _process_content_line(state, "@@end\n", code_file_manager)


async def _process_content_line(state, content, code_file_manager: CodeFileManager):
    stream = get_session_stream()

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
            await stream.send(prefix + to_print, end="", color=color)

    if "\n" in content:
        (
            to_print,
            entered_code_lines,
            exited_code_lines,
            created_code_change,
        ) = state.new_line(code_file_manager)

        if created_code_change:
            cur_change = state.code_changes[-1]
            if cur_change.error:
                logging.info(
                    f"Model error when creating code change: {cur_change.error}"
                )
                await stream.send("Not showing skipped change due to error:")
                await stream.send(cur_change.error, color="red")
                await stream.send("Continuing model response...", color="light_green")

            else:
                if (
                    len(state.code_changes) < 2
                    or state.code_changes[-2].file != cur_change.file
                    or state.explained_since_change
                    or state.code_changes[-1].action == CodeChangeAction.RenameFile
                ):
                    await print_file_name(cur_change)
                    if (
                        cur_change.action.has_additions()
                        or cur_change.action.has_removals()
                    ):
                        await stream.send(change_delimiter)
                state.explained_since_change = False
                await print_previous_lines(cur_change)
                await print_removed_block(cur_change)
                if (
                    not cur_change.action.has_additions()
                    and cur_change.action.has_removals()
                ):
                    await print_later_lines(cur_change)
                    await stream.send(change_delimiter)

        if to_print and not (state.in_code_lines and state.code_changes[-1].error):
            prefix = (
                "+" + " " * (state.code_changes[-1].line_number_buffer - 1)
                if state.in_code_lines and beginning
                else ""
            )
            color = "green" if state.in_code_lines else None
            await stream.send(prefix + to_print, end="", color=color)
        if exited_code_lines and not state.code_changes[-1].error:
            await print_later_lines(state.code_changes[-1])
            await stream.send(change_delimiter)
