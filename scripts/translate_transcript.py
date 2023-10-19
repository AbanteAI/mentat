#!/usr/bin/env python
import argparse
import asyncio
import json
from unittest.mock import AsyncMock
from pathlib import Path

from mentat.code_file_manager import CODE_FILE_MANAGER, CodeFileManager
from mentat.git_handler import GIT_ROOT
from mentat.parsers.block_parser import BlockParser
from mentat.parsers.parser import Parser
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.parsers.split_diff_parser import SplitDiffParser
from mentat.parsers.unified_diff_parser import UnifiedDiffParser
from mentat.parsers.git_parser import GitParser
from mentat.session_stream import SESSION_STREAM
from mentat.utils import convert_string_to_asyncgen


parser_map: dict[str, Parser] = {
    "block": BlockParser(),
    "replacement": ReplacementParser(),
    "split-diff": SplitDiffParser(),
    "unified-diff": UnifiedDiffParser(),
    "git": GitParser(),
}


def translate_message(message: str, starting_parser, ending_parser) -> str:
    if hasattr(starting_parser, "parse_string"):
        parsedLLMResponse = starting_parser.parse_string(message)
    else:
        parsedLLMResponse = asyncio.run(
            starting_parser.stream_and_parse_llm_response(
                convert_string_to_asyncgen(message, 100)
            )
        )
    return ending_parser.file_edits_to_llm_message(parsedLLMResponse)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Translate transcript between parsing formats"
    )
    parser.add_argument(
        "--transcript", type=str, default=None, help="Transcript to translate"
    )
    parser.add_argument(
        "--starting-format",
        type=str,
        default="block",
        help="Format of the transcript to translate",
    )
    parser.add_argument(
        "--ending-format", type=str, default="block", help="Format to translate to"
    )
    parser.add_argument("--git-root", type=str, default=".", help="Git root directory")
    args = parser.parse_args()

    GIT_ROOT.set(Path(args.git_root))
    CODE_FILE_MANAGER.set(CodeFileManager())
    SESSION_STREAM.set(AsyncMock())

    starting_parser = parser_map[args.starting_format]
    ending_parser = parser_map[args.ending_format]
    with open(args.transcript, "r") as f:
        if ".json" in args.transcript:
            for line in f.readlines():
                transcript = json.loads(line)
                messages = transcript["messages"]
                for message in messages:
                    # Note we don't change the system prompts. In training they are stripped off anyway.
                    if message["role"] == "assistant":
                        message["content"] = translate_message(
                            message["content"], starting_parser, ending_parser
                        )

                print(json.dumps(transcript))
        else:
            print(translate_message(f.read(), starting_parser, ending_parser))
