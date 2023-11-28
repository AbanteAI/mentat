import asyncio
from asyncio import Task
import wave
from typing import Any, Optional

import pyaudio
import sounddevice  # type: ignore # noqa: F401 Suppresses pyaudio output
from openai import OpenAI
from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory, Suggestion
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent

from mentat.utils import mentat_dir_path

AUDIO_FILE = "temp.wav"
CHUNK = 256
RATE = 44100
WHISPER_BATCH_SECS = 2
NUM_CHUNKS = 24000
MAX_SECONDS = 10
audio = pyaudio.PyAudio()


def write_audio(data: list[bytes]) -> None:
    waveFile = wave.open(AUDIO_FILE, "wb")
    waveFile.setnchannels(1)
    waveFile.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
    waveFile.setframerate(RATE)
    waveFile.writeframes(b"".join(data))
    waveFile.close()


async def call_whisper(start_text: str, buffer: Buffer) -> None:
    client = OpenAI()

    audio_file = open(AUDIO_FILE, "rb")
    transcript = client.audio.transcriptions.create(
        model="whisper-1", file=audio_file, response_format="text"
    )

    # Openai says transcript should be type Transcript which has one attribute text but in fact it's just a string.
    buffer.text = (start_text + " " + transcript).strip() # pyright: ignore


async def transcribe_audio(session: PromptSession[str], buffer: Buffer) -> None:
    start_text = buffer.text
    data = []
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=RATE,
        input=True,
        input_device_index=3,
        frames_per_buffer=CHUNK * 50,
    )
    last_whisper_run = 0
    whisper_job = None
    try:
        for i in range(NUM_CHUNKS):
            if i * CHUNK / RATE > MAX_SECONDS:
                break
            data.append(stream.read(CHUNK)) # pyright: ignore
            if (i - last_whisper_run) * CHUNK / RATE > WHISPER_BATCH_SECS:
                last_whisper_run = i
                write_audio(data)
                if whisper_job is None or whisper_job.done():
                    whisper_job = asyncio.create_task(
                        call_whisper(start_text, buffer)
                    )
            await asyncio.sleep(0)  # Yield control to the event loop
    finally:
        stream.close()
        write_audio(data)
        if whisper_job is not None and not whisper_job.done():
            whisper_job.cancel()
        await call_whisper(start_text, buffer)
        session.message = '>>> '
        get_app().invalidate()


class FilteredFileHistory(FileHistory):
    def __init__(self, filename: str):
        self.excluded_phrases = ["y", "n", "i", "q"]
        super().__init__(filename)

    def append_string(self, string: str):
        if string.strip().lower() not in self.excluded_phrases and string.strip():
            super().append_string(string)


class FilteredHistorySuggestions(AutoSuggestFromHistory):
    def __init__(self):
        super().__init__()

    def get_suggestion(self, buffer: Buffer, document: Document) -> Suggestion | None:
        # We want the auto completer to handle commands instead of the suggester
        if buffer.text[0] == "/":
            return None
        else:
            return super().get_suggestion(buffer, document)


class MentatPromptSession(PromptSession[str]):
    def __init__(self, *args: Any, **kwargs: Any):
        self._setup_bindings()
        super().__init__(
            message=[("class:prompt", ">>> ")],
            history=FilteredFileHistory(str(mentat_dir_path.joinpath("history"))),
            auto_suggest=FilteredHistorySuggestions(),
            multiline=True,
            prompt_continuation=self.prompt_continuation,
            key_bindings=self.bindings,
            *args,
            **kwargs,
        )
        self._transcription: Optional[Task[None]] = None

    def prompt_continuation(
        self, width: int, line_number: int, is_soft_wrap: int
    ) -> AnyFormattedText:
        return (
            "" if is_soft_wrap else [("class:continuation", " " * (width - 2) + "> ")]
        )

    def _setup_bindings(self):
        self.bindings = KeyBindings()

        @self.bindings.add("s-down")
        @self.bindings.add("c-j")
        def _(event: KeyPressEvent):
            event.current_buffer.insert_text("\n")

        @self.bindings.add("enter")
        def _(event: KeyPressEvent):
            event.current_buffer.validate_and_handle()

        @Condition
        def complete_suggestion() -> bool:
            app = get_app()
            return (
                app.current_buffer.suggestion is not None
                and len(app.current_buffer.suggestion.text) > 0
                and app.current_buffer.document.is_cursor_at_the_end
                and bool(app.current_buffer.text)
                and app.current_buffer.text[0] != "/"
            )

        @self.bindings.add("right", filter=complete_suggestion)
        def _(event: KeyPressEvent):
            suggestion = event.current_buffer.suggestion
            if suggestion:
                event.current_buffer.insert_text(suggestion.text)

        @self.bindings.add("c-c")
        @self.bindings.add("c-d")
        def _(event: KeyPressEvent):
            if event.current_buffer.text != "":
                event.current_buffer.reset()
            else:
                event.app.exit(result="q")

        @self.bindings.add("c-u")
        def _(event: KeyPressEvent):
            if self._transcription is None or self._transcription.done():
                self.message = "(Transcribing audio. c-u to stop) "
                event.app.invalidate()
                self._transcription = asyncio.create_task(
                    transcribe_audio(self, event.current_buffer)
                )
            else:
                if not self._transcription.done():
                    self._transcription.cancel()
                    self._transcription = None
