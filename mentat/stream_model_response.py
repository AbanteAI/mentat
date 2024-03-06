from __future__ import annotations

import asyncio
import json
import logging
from difflib import ndiff
from json import JSONDecodeError
from pathlib import Path
from typing import AsyncIterator

from openai.types.chat import (
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)
from openai.types.chat.completion_create_params import ResponseFormat

from mentat.llm_api_handler import TOKEN_COUNT_WARNING, count_tokens, prompt_tokens
from mentat.parsers.parser import ParsedLLMResponse
from mentat.parsers.streaming_printer import StreamingPrinter
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import add_newline

two_step_edit_prompt_filename = Path("two_step_edit_prompt.txt")
two_step_edit_prompt_list_files_filename = Path("two_step_edit_prompt_list_files.txt")
two_step_edit_prompt_rewrite_file_filename = Path(
    "two_step_edit_prompt_rewrite_file.txt"
)


async def stream_model_response(
    messages: list[ChatCompletionMessageParam],
) -> ParsedLLMResponse:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    code_file_manager = session_context.code_file_manager
    config = session_context.config
    parser = config.parser
    llm_api_handler = session_context.llm_api_handler
    cost_tracker = session_context.cost_tracker

    num_prompt_tokens = prompt_tokens(messages, config.model)
    stream.send(f"Total token count: {num_prompt_tokens}", style="info")
    if num_prompt_tokens > TOKEN_COUNT_WARNING:
        stream.send(
            "Warning: LLM performance drops off rapidly at large context sizes. Use"
            " /clear to clear context or use /exclude to exclude any uneccessary"
            " files.",
            style="warning",
        )

    stream.send(
        None,
        channel="loading",
    )
    response = await llm_api_handler.call_llm_api(
        messages,
        config.model,
        stream=True,
        response_format=parser.response_format(),
    )
    stream.send(
        None,
        channel="loading",
        terminate=True,
    )

    stream.send("Streaming... use control-c to interrupt the model at any point\n")
    async with parser.interrupt_catcher():
        parsed_llm_response = await parser.stream_and_parse_llm_response(
            add_newline(response)
        )
    # Sampler and History require previous_file_lines
    for file_edit in parsed_llm_response.file_edits:
        file_edit.previous_file_lines = code_file_manager.file_lines.get(
            file_edit.file_path, []
        )
    if not parsed_llm_response.interrupted:
        cost_tracker.display_last_api_call()
    else:
        # Generator doesn't log the api call if we interrupt it
        cost_tracker.log_api_call_stats(
            num_prompt_tokens,
            count_tokens(
                parsed_llm_response.full_response, config.model, full_message=False
            ),
            config.model,
            display=True,
        )

    return parsed_llm_response


def get_two_step_system_prompt() -> str:
    return read_prompt(two_step_edit_prompt_filename)


def get_two_step_list_files_prompt() -> str:
    return read_prompt(two_step_edit_prompt_list_files_filename)


def get_two_step_rewrite_file_prompt() -> str:
    return read_prompt(two_step_edit_prompt_rewrite_file_filename)


def print_colored_diff(str1, str2, stream):
    diff = ndiff(str1.splitlines(), str2.splitlines())

    for line in diff:
        if line.startswith("-"):
            stream.send(line, color="red")
        elif line.startswith("+"):
            stream.send(line, color="green")
        elif line.startswith("?"):
            pass  # skip printing the ? lines ndiff produces
        else:
            stream.send(line)


async def stream_model_response_two_step(
    messages: list[ChatCompletionMessageParam],
) -> ParsedLLMResponse:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    code_file_manager = session_context.code_file_manager
    config = session_context.config
    parser = config.parser
    llm_api_handler = session_context.llm_api_handler
    cwd = session_context.cwd

    num_prompt_tokens = prompt_tokens(messages, config.model)
    stream.send(f"Total token count: {num_prompt_tokens}", style="info")
    if num_prompt_tokens > TOKEN_COUNT_WARNING:
        stream.send(
            "Warning: LLM performance drops off rapidly at large context sizes. Use"
            " /clear to clear context or use /exclude to exclude any uneccessary"
            " files.",
            style="warning",
        )

    stream.send(
        None,
        channel="loading",
    )
    response = await llm_api_handler.call_llm_api(
        messages,
        config.model,
        stream=True,
        response_format=parser.response_format(),
    )
    stream.send(
        None,
        channel="loading",
        terminate=True,
    )

    # TODO: if using two step, don't add line numbers to context - might help
    # TODO: identify files mentioned, rewrite them with new calls
    # TODO: instead of FileEdit objects, return new rewritten files?
    # TODO: add interrupt ability
    # TODO: make sure to track costs of all calls and log api calls
    stream.send("Streaming... use control-c to interrupt the model at any point\n")
    first_message = await stream_and_parse_llm_response_two_step(response)

    stream.send(
        "\n\n### Initial Response Complete - parsing edits: ###\n", style="info"
    )

    list_files_messages: list[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(
            role="system",
            content=get_two_step_list_files_prompt(),
        ),
        ChatCompletionSystemMessageParam(
            role="system",
            content=first_message,
        ),
    ]

    list_files_response = await llm_api_handler.call_llm_api(
        list_files_messages,
        model="gpt-3.5-turbo-0125",  # TODO add config for secondary model
        stream=False,
        response_format=ResponseFormat(type="json_object"),
    )

    try:
        response_json = json.loads(list_files_response.choices[0].message.content)
    except JSONDecodeError:
        stream.send("Error processing model response: Invalid JSON", style="error")
        # TODO: handle error

    stream.send(f"\n{response_json}\n")

    # TODO remove line numbers when running two step edit
    # TODO handle creating new files - including update prompt to know that's possible

    rewritten_files = []
    for file_path in response_json["files"]:
        full_path = (cwd / Path(file_path)).resolve()
        code_file_lines = code_file_manager.file_lines.get(full_path, [])
        code_file_string = "\n".join(code_file_lines)

        rewrite_file_messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(
                role="system",
                content=get_two_step_rewrite_file_prompt(),
            ),
            ChatCompletionSystemMessageParam(
                role="system",
                content=code_file_string,
            ),
            ChatCompletionSystemMessageParam(
                role="system",  # TODO: change to user? not sure
                content=first_message,
            ),
        ]

        rewrite_file_response = await llm_api_handler.call_llm_api(
            rewrite_file_messages,
            model="gpt-3.5-turbo-0125",  # TODO add config for secondary model
            stream=False,
        )
        rewrite_file_response = rewrite_file_response.choices[0].message.content
        lines = rewrite_file_response.splitlines()
        # TODO remove asserts
        assert "```" in lines[0]
        assert "```" in lines[-1]
        lines = lines[1:-1]
        rewrite_file_response = "\n".join(lines)

        rewritten_files.append((full_path, rewrite_file_response))

        stream.send(f"\n### File Rewrite Response: {file_path} ###\n")
        # stream.send(rewrite_file_response)

        # TODO stream colored diff, skipping unchanged lines (except some for context)
        print_colored_diff(code_file_string, rewrite_file_response, stream)

    # async with parser.interrupt_catcher():
    #     parsed_llm_response = await parser.stream_and_parse_llm_response(
    #         add_newline(response)
    #     )

    # # Sampler and History require previous_file_lines
    # for file_edit in parsed_llm_response.file_edits:
    #     file_edit.previous_file_lines = code_file_manager.file_lines.get(
    #         file_edit.file_path, []
    #     )
    # if not parsed_llm_response.interrupted:
    #     cost_tracker.display_last_api_call()
    # else:
    #     # Generator doesn't log the api call if we interrupt it
    #     cost_tracker.log_api_call_stats(
    #         num_prompt_tokens,
    #         count_tokens(
    #             parsed_llm_response.full_response, config.model, full_message=False
    #         ),
    #         config.model,
    #         display=True,
    #     )

    return ParsedLLMResponse(
        full_response=first_message,
        conversation=first_message,
        # [file_edit for file_edit in file_edits.values()],
        file_edits=[],
        rewritten_files=rewritten_files,
        interrupted=False,
    )


async def stream_and_parse_llm_response_two_step(
    response: AsyncIterator[ChatCompletionChunk],
) -> str:
    printer = StreamingPrinter()
    printer_task = asyncio.create_task(printer.print_lines())

    message = ""

    async for chunk in response:
        # if self.shutdown.is_set():
        #     interrupted = True
        #     printer.shutdown_printer()
        #     if printer_task is not None:
        #         await printer_task
        #     stream.send("\n\nInterrupted by user. Using the response up to this point.")
        #     break

        content = ""
        if len(chunk.choices) > 0:
            content = chunk.choices[0].delta.content or ""

        message += content
        printer.add_string(content, end="")

    # Only finish printing if we don't quit from ctrl-c
    printer.wrap_it_up()
    if printer_task is not None:
        await printer_task

    logging.debug("LLM Response:")
    logging.debug(message)

    return message
