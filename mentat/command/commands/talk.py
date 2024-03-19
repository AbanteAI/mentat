import asyncio
import queue
from asyncio import Event
from timeit import default_timer
from typing import Any, List

import numpy as np
from typing_extensions import override

try:
    import sounddevice as sd
    import soundfile as sf

    audio_available = True
except Exception:
    audio_available = False


from mentat.command.command import Command, CommandArgument
from mentat.logging_config import logs_path
from mentat.session_context import SESSION_CONTEXT

RATE = 16000


class Recorder:
    def __init__(self):
        self.shutdown = Event()
        (logs_path / "audio").mkdir(parents=True, exist_ok=True)

        self.file = logs_path / "audio/talk_transcription.wav"

    def callback(
        self,
        in_data: np.ndarray[Any, Any],
        frames: int,
        time: Any,
        status: int,
    ):
        self.q.put(in_data.copy())

    async def record(self):
        self.start_time = default_timer()

        self.q: queue.Queue[np.ndarray[Any, Any]] = queue.Queue()
        with sf.SoundFile(  # pyright: ignore[reportUnboundVariable]
            self.file, mode="w", samplerate=RATE, channels=1
        ) as file:
            with sd.InputStream(  # pyright: ignore[reportUnboundVariable]
                samplerate=RATE, channels=1, callback=self.callback
            ):
                while not self.shutdown.is_set():
                    await asyncio.sleep(0)
                    file.write(self.q.get())  # type: ignore

        self.recording_time = default_timer() - self.start_time


class TalkCommand(Command, command_name="talk"):
    @override
    async def apply(self, *args: str) -> None:
        ctx = SESSION_CONTEXT.get()
        if not audio_available:
            # sounddevice manages port audio on Mac and Windows so we print an apt specific message
            ctx.stream.send(
                "Audio is not available on this system. You probably need to install"
                " PortAudio. For example `sudo apt install libportaudio2` on Ubuntu.",
                style="error",
            )
        else:
            # TODO: Ctrl+C doesn't make sense for VSCode client. Send this info in a client agnostic way
            ctx.stream.send("Listening on your default microphone. Press Ctrl+C to end.")
            recorder = Recorder()
            async with ctx.stream.interrupt_catcher(recorder.shutdown):
                await recorder.record()
            ctx.stream.send("Processing audio with whisper...")
            await asyncio.sleep(0.01)
            transcript = await ctx.llm_api_handler.call_whisper_api(recorder.file)
            ctx.stream.send(transcript, channel="default_prompt")
            ctx.cost_tracker.log_whisper_call_stats(recorder.recording_time)

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return []

    @override
    @classmethod
    def argument_autocompletions(cls, arguments: list[str], argument_position: int) -> list[str]:
        return []

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Start voice to text."
