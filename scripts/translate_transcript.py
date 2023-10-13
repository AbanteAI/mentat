#!/usr/bin/env python
import argparse
import asyncio
import json
from unittest.mock import AsyncMock

from mentat.code_file_manager import CODE_FILE_MANAGER, CodeFileManager
from mentat.git_handler import GIT_ROOT
from mentat.parsers.block_parser import BlockParser
from mentat.parsers.parser import Parser
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.parsers.split_diff_parser import SplitDiffParser
from mentat.parsers.unified_diff_parser import UnifiedDiffParser
from mentat.session_stream import SESSION_STREAM
from mentat.utils import convert_string_to_asyncgen

GIT_ROOT.set(".")
CODE_FILE_MANAGER.set(CodeFileManager())
SESSION_STREAM.set(AsyncMock())


parser_map: dict[str, Parser] = {
    "block": BlockParser(),
    "replacement": ReplacementParser(),
    "split-diff": SplitDiffParser(),
    "unified-diff": UnifiedDiffParser(),
}

parser = argparse.ArgumentParser(
    description="Translate transcript between parsing formats"
)
parser.add_argument(
    "--transcript", type=str, default=None, help="Transcript to translate"
)
# TODO: infer from config or something
parser.add_argument(
    "--starting-format",
    type=str,
    default="block",
    help="Format of the transcript to translate",
)
parser.add_argument(
    "--ending-format", type=str, default="block", help="Format to translate to"
)
args = parser.parse_args()

starting_parser = parser_map[args.starting_format]
ending_parser = parser_map[args.ending_format]

with open(args.transcript, "r") as f:
    for line in f.readlines():
        transcript = json.loads(line)
        messages = transcript["messages"]
        for message in messages:
            # Note we don't change the system prompts. In training they are stripped off anyway.
            if message["role"] == "assistant":
                content = message["content"]
                file_edits = asyncio.run(
                    starting_parser.stream_and_parse_llm_response(
                        convert_string_to_asyncgen(content, 100)
                    )
                )
                message["content"] = ending_parser.file_edits_to_llm_message(file_edits)

        print(json.dumps(transcript))
