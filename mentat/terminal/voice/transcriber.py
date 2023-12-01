import os
import wave
from typing import Iterable, Mapping, Tuple

import pyaudio
import sounddevice  # type: ignore # noqa: F401 Suppresses pyaudio output
from faster_whisper import WhisperModel
from faster_whisper.transcribe import Segment
from prompt_toolkit.buffer import Buffer

from mentat.utils import mentat_dir_path

AUDIO_FILE = mentat_dir_path / "temp.wav"
CHUNK = 256
RATE = 44100
WHISPER_BATCH_SECS = 1.5
NUM_CHUNKS = 24000
MAX_SECONDS = 300
audio = pyaudio.PyAudio()


def write_audio(data: list[bytes]) -> None:
    waveFile = wave.open(str(AUDIO_FILE), "wb")
    waveFile.setnchannels(1)
    waveFile.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
    waveFile.setframerate(RATE)
    waveFile.writeframes(b"".join(data))
    waveFile.close()


def segments_to_transcript(segments: Iterable[Segment]):
    transcript = ""
    segments = [segment for segment in segments]

    if len(segments) == 0:
        return "", "", 0

    end = segments[-1].end
    fixed_transcript = ""
    time = 0
    for segment in segments:
        if segment.end < end - 4:
            time = segment.end
            fixed_transcript += segment.text + " "
        transcript += segment.text + " "

    return transcript, fixed_transcript, time


class Transcriber:
    def __init__(self, buffer: Buffer) -> None:
        self.data: list[bytes] = []
        self.buffer = buffer
        self.start_text = buffer.text
        self.fixed = ""
        # Runs well on CPU. And works well for me if I speak clearly.
        # We should allow it to be user configurable.
        self.whisper_model_size = "tiny"
        # Necessary to suppress faster_whisper logging
        os.environ["CT2_VERBOSE"] = "-3"
        self.whisper_model = WhisperModel(self.whisper_model_size)
        # The transcript before this timestamp won't be changed
        self.frozen_timestamp = 0
        # How many frames are represented in the transcript
        self.processed_frames = 0
        self.whisper_semafore = False
        default_device_index = audio.get_default_input_device_info().get("index")
        if not isinstance(default_device_index, int):
            default_device_index = None
        self.stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=RATE,
            input=True,
            input_device_index=default_device_index,
            frames_per_buffer=CHUNK * 50,
            stream_callback=self.callback,
        )
        self.stream.start_stream()

    def callback(
        self,
        in_data: bytes | None,
        frame_count: int,
        time_info: Mapping[str, float],
        status: int,
    ) -> Tuple[None, int]:
        if in_data:
            self.data.append(in_data)
            write_audio(self.data)
            if not self.whisper_semafore:
                if (
                    len(self.data) - self.processed_frames
                ) * frame_count / RATE > WHISPER_BATCH_SECS:
                    self.call_whisper()
        return (None, pyaudio.paContinue)

    def call_whisper(self) -> None:
        self.whisper_semafore = True
        self.processed_frames = len(self.data)
        TEMP_AUDIO_FILE = mentat_dir_path / "temp2.wav"
        with wave.open(str(AUDIO_FILE), "rb") as wave_file:
            start = int(RATE * self.frozen_timestamp)
            length = wave_file.getnframes()
            wave_file.setpos(start)
            frames = wave_file.readframes(length - start)
            with wave.open(str(TEMP_AUDIO_FILE), "wb") as wave_file2:
                wave_file2.setnchannels(1)
                wave_file2.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
                wave_file2.setframerate(RATE)
                wave_file2.writeframes(frames)
        segments, _ = self.whisper_model.transcribe(
            str(TEMP_AUDIO_FILE), beam_size=5, language="en", prefix=self.fixed
        )
        transcript, fixed_transcript, end = segments_to_transcript(segments)
        self.frozen_timestamp += end

        self.buffer.text = (
            self.start_text + " " + self.fixed + " " + transcript
        ).strip()

        self.fixed += fixed_transcript
        self.whisper_semafore = False

    async def close(self):
        self.stream.stop_stream()
        self.stream.close()
