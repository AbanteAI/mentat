import datetime
import glob
import json
import logging
import re

from openai.types.chat import ChatCompletionMessageParam

from mentat.llm_api_handler import is_test_environment
from mentat.utils import mentat_dir_path

logs_dir = "logs"
logs_path = mentat_dir_path / logs_dir


def setup_logging():
    if is_test_environment():
        return

    logging.getLogger("openai").setLevel(logging.WARNING)
    # Breaking out of async generator when model messes up causes an error
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Root logger
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    # Only log warnings and higher to console
    console_handler.setLevel(logging.WARNING)

    logs_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_path / f"mentat_{timestamp}.log"
    latest_log_file = logs_path / "latest.log"
    latest_log_file.unlink(missing_ok=True)

    file_handler = logging.FileHandler(log_file)
    file_handler_latest = logging.FileHandler(latest_log_file)
    file_handler.setFormatter(formatter)
    file_handler_latest.setFormatter(formatter)

    handlers = [console_handler, file_handler, file_handler_latest]

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        root.addHandler(handler)

    # Costs logger
    costs_logger = logging.getLogger("costs")
    for handler in costs_logger.handlers[:]:
        costs_logger.removeHandler(handler)
        handler.close()
    costs_formatter = logging.Formatter("%(asctime)s\n%(message)s")
    costs_handler = logging.FileHandler(logs_path / "costs.log")
    costs_handler.setFormatter(costs_formatter)
    costs_logger.addHandler(costs_handler)
    costs_logger.setLevel(logging.INFO)
    costs_logger.propagate = False

    # Transcript logger
    transcripts_logger = logging.getLogger("transcript")
    for handler in transcripts_logger.handlers[:]:
        transcripts_logger.removeHandler(handler)
        handler.close()
    transcripts_formatter = logging.Formatter("%(message)s")
    transcripts_handler = logging.FileHandler(logs_path / f"transcript_{timestamp}.log")
    transcripts_handler.setFormatter(transcripts_formatter)
    transcripts_logger.addHandler(transcripts_handler)
    transcripts_logger.setLevel(logging.INFO)
    transcripts_logger.propagate = False


def get_transcript_logs() -> (
    list[tuple[str, list[tuple[str, list[ChatCompletionMessageParam] | None]]]]
):
    transcripts = glob.glob(str(logs_path / "transcript_*"))
    ans = list[tuple[str, list[tuple[str, list[ChatCompletionMessageParam] | None]]]]()
    for transcript_path in transcripts:
        match = re.search(r"transcript_(.+).log", transcript_path)
        if match is None:
            continue
        timestamp = match.group(1)

        with open(transcript_path, "r") as f:
            transcript = f.readlines()
        if len(transcript) == 0:
            continue

        # TODO: Test if this still works (despite not being explicitly converted to ChatCompletionMessageParam)
        transcript = json.loads("[" + ", ".join(transcript) + "]")
        ans.append((timestamp, transcript))
    return sorted(ans, key=lambda x: x[0], reverse=True)
