import asyncio
import json
import logging
from json import JSONDecodeError
from pathlib import Path
from typing import AsyncIterator, Dict

from jsonschema import ValidationError, validate
from openai.types.chat.completion_create_params import ResponseFormat
from typing_extensions import override

from mentat.errors import ModelError
from mentat.llm_api_handler import chunk_to_lines
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.parser import ParsedLLMResponse, Parser
from mentat.parsers.streaming_printer import StreamingPrinter
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT

json_parser_prompt_filename = Path("json_parser_prompt.txt")

comment_schema = {
    "type": "object",
    "properties": {"type": {"enum": ["comment"]}, "content": {"type": "string"}},
}

edit_schema = {
    "type": "object",
    "properties": {
        "type": {"enum": ["edit"]},
        "filename": {"type": "string"},
        "starting-line": {"type": "integer"},
        "ending-line": {"type": "integer"},
        "content": {"type": "string"},
    },
}

creation_schema = {
    "type": "object",
    "properties": {
        "type": {"enum": ["creation"]},
        "filename": {"type": "string"},
    },
}

deletion_schema = {
    "type": "object",
    "properties": {
        "type": {"enum": ["deletion"]},
        "filename": {"type": "string"},
    },
}

rename_schema = {
    "type": "object",
    "properties": {
        "type": {"enum": ["rename"]},
        "filename": {"type": "string"},
        "new-filename": {"type": "string"},
    },
}

output_schema = {
    "type": "object",
    "properties": {
        "content": {
            "type": "array",
            "items": {
                "anyOf": [
                    comment_schema,
                    edit_schema,
                    creation_schema,
                    deletion_schema,
                    rename_schema,
                ]
            },
        }
    },
}


class JsonParser(Parser):
    @override
    def get_system_prompt(self) -> str:
        return read_prompt(json_parser_prompt_filename)

    @override
    def response_format(self) -> ResponseFormat:
        return ResponseFormat(type="json_object")

    @override
    def line_number_starting_index(self) -> int:
        return 0

    @override
    async def stream_and_parse_llm_response(self, response: AsyncIterator[str]) -> ParsedLLMResponse:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        printer = StreamingPrinter()
        printer_task = asyncio.create_task(printer.print_lines())
        message = ""
        conversation = ""
        rename_map: Dict[Path, Path] = {}
        async for chunk in response:
            if self.shutdown.is_set():
                printer.shutdown_printer()
                await printer_task
                stream.send("\n\nInterrupted by user. Using the response up to this point.")
                break

            for content in chunk_to_lines(chunk):
                if not content:
                    continue
                message += content
                printer.add_string(content, end="")
        else:
            # Only finish printing if we don't quit from ctrl-c
            printer.wrap_it_up()
            await printer_task
        logging.debug("LLM Response:")
        logging.debug(message)

        try:
            response_json = json.loads(message)
            validate(instance=response_json, schema=output_schema)
        except JSONDecodeError:
            # Should never happen with OpenAI's response_format set to json
            stream.send("Error processing model response: Invalid JSON", style="error")
            return ParsedLLMResponse(message, "", [])
        except ValidationError:
            stream.send("Error processing model response: Invalid format given", style="error")
            return ParsedLLMResponse(message, "", [])

        file_edits: Dict[Path, FileEdit] = {}
        for obj in response_json["content"]:
            filename = (session_context.cwd / obj.get("filename", "")).resolve()
            if filename in rename_map:
                filename = rename_map[filename]
            match obj["type"]:
                case "comment":
                    conversation += obj["content"]
                    fileedit = None
                case "edit":
                    fileedit = FileEdit(
                        filename,
                        [
                            Replacement(
                                obj["starting-line"] - 1,
                                obj["ending-line"] - 1,
                                obj["content"].split("\n"),
                            )
                        ],
                        False,
                        False,
                        None,
                    )
                case "creation":
                    fileedit = FileEdit(filename, [], True, False, None)
                case "deletion":
                    fileedit = FileEdit(filename, [], False, True, None)
                case "rename":
                    new_filename = session_context.cwd / obj["new-filename"]
                    fileedit = FileEdit(filename, [], False, False, new_filename)
                    rename_map[new_filename] = filename
                case _:
                    # Should never happen with JSON validation
                    raise ModelError("Invalid JSON type")
            if fileedit is None:
                continue
            if filename not in file_edits:
                file_edits[filename] = fileedit
            else:
                # TODO: Add merge function to fileedit
                old_fileedit = file_edits[filename]
                file_edits[filename] = FileEdit(
                    filename,
                    fileedit.replacements + old_fileedit.replacements,
                    fileedit.is_creation or old_fileedit.is_creation,
                    fileedit.is_deletion or old_fileedit.is_deletion,
                    (
                        fileedit.rename_file_path
                        if fileedit.rename_file_path is not None
                        else old_fileedit.rename_file_path
                    ),
                )

        return ParsedLLMResponse(
            message,
            conversation,
            [file_edit for file_edit in file_edits.values()],
        )
