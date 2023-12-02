import json
import webbrowser
from pathlib import Path

import fire  # pyright: ignore[reportMissingTypeStubs]

from mentat.utils import create_viewer


# Currently will NOT work; because the /conversation command works well, no need to update
def transcript_viewer(transcript_location: str):
    transcript_path = Path(transcript_location)
    with transcript_path.open("r") as transcript_file:
        transcript = transcript_file.read().strip()
    literal_messages: list[tuple[str, list[dict[str, str]] | None]] = [
        json.loads(line) for line in transcript.split("\n")
    ]
    viewer_path = create_viewer(literal_messages)
    webbrowser.open(f"file://{viewer_path.resolve()}")


if __name__ == "__main__":
    fire.Fire(transcript_viewer)  # pyright: ignore[reportUnknownMemberType]
