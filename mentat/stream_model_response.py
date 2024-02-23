from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

from openai.types.chat import ChatCompletionChunk, ChatCompletionMessageParam

from mentat.llm_api_handler import TOKEN_COUNT_WARNING, count_tokens, prompt_tokens
from mentat.parsers.parser import ParsedLLMResponse
from mentat.parsers.streaming_printer import FormattedString, StreamingPrinter
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import add_newline

two_step_edit_prompt_filename = Path("two_step_edit_prompt.txt")


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


async def stream_model_response_two_step(
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

    # TODO: identify files mentioned, rewrite them with new calls
    # TODO: add interrupt ability
    # TODO: make sure to track costs of all calls and log api calls
    stream.send("Streaming... use control-c to interrupt the model at any point\n")
    first_message = await stream_and_parse_llm_response_two_step(response)

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
        interrupted=False,
    )


async def stream_and_parse_llm_response_two_step(
    response: AsyncIterator[ChatCompletionChunk],
) -> str:
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
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
