import glob
import json
import re
from typing import TypedDict

from openai.types.chat import ChatCompletionContentPartParam, ChatCompletionMessageParam

from mentat.logging_config import logs_path


class UserMessage(TypedDict):
    message: list[ChatCompletionContentPartParam] | str
    # We need this field so that it is included when we convert to JSON
    prior_messages: None


class ModelMessage(TypedDict, total=False):
    message: str
    prior_messages: list[ChatCompletionMessageParam]

    # Used to mark different types of messages; e.g., an agent message that isn't part of the regular conversation
    # NotRequired isn't available until 3.11, so we have to use total=False instead
    message_type: str


TranscriptMessage = UserMessage | ModelMessage


class Transcript(TypedDict):
    id: str
    messages: list[TranscriptMessage]


def get_transcript_logs() -> list[Transcript]:
    transcripts = glob.glob(str(logs_path / "transcript_*"))
    ans = list[Transcript]()
    for transcript_path in transcripts:
        match = re.search(r"transcript_(.+).log", transcript_path)
        if match is None:
            continue
        timestamp = match.group(1)

        with open(transcript_path, "r") as f:
            transcript = f.readlines()
        if len(transcript) == 0:
            continue

        transcript = json.loads("[" + ", ".join(transcript) + "]")
        ans.append(Transcript(id=timestamp, messages=transcript))

    return sorted(ans, key=lambda x: x["id"], reverse=True)
