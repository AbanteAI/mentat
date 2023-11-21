import glob
import json
import re
from typing import TypedDict

from openai.types.chat import ChatCompletionMessageParam

from mentat.logging_config import logs_path


class UserMessage(TypedDict):
    message: str
    # We need this field so that it is included when we convert to JSON
    prior_messages: None


class ModelMessage(TypedDict):
    message: str
    prior_messages: list[ChatCompletionMessageParam]


TranscriptMessage = UserMessage | ModelMessage


class Transcript(TypedDict):
    timestamp: str
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
        ans.append(Transcript(timestamp=timestamp, messages=transcript))

    return sorted(ans, key=lambda x: x["timestamp"], reverse=True)
