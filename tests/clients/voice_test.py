from unittest.mock import Mock

import numpy as np

from mentat.terminal.voice.transcriber import (
    CHUNK,
    DELAY_TO_FREEZE,
    RATE,
    REAL_TIME_THRESHOLD,
    WHISPER_BATCH_SECS,
    Transcriber,
)


def test_transcriber_with_frozen_timestamp(mocker):
    try:
        mocker.patch("mentat.terminal.voice.transcriber.sd")
    except AttributeError:
        return  # Test skipped on Ubuntu
    mock_whisper_model = mocker.patch("mentat.terminal.voice.transcriber.WhisperModel")

    mock_buffer = Mock()
    mock_buffer.text = ""

    transcriber = Transcriber(buffer=mock_buffer)

    segment_one_two = [
        Mock(
            words=[
                Mock(word="one ", start=0.0, end=0.5),
                Mock(word="2 ", start=0.6, end=DELAY_TO_FREEZE + 0.5),
            ],
            end=DELAY_TO_FREEZE + 0.5,
        )
    ]
    segment_two_three = [
        Mock(
            words=[
                Mock(word="two ", start=1.1, end=1.5),
                Mock(word="three ", start=1.6, end=2.0),
            ],
            end=2.0,
        )
    ]
    final_segment = [Mock(words=[Mock(word="elephant ", start=1.1, end=1.5)], end=2.0)]
    mock_whisper_model.return_value.transcribe.side_effect = [
        (segment_one_two, None),
        (segment_two_three, None),
        (final_segment, None),
    ]

    in_data = np.array([0.0] * CHUNK)
    time_info = Mock(currentTime=0.0, inputBufferAdcTime=0.0)

    # Waits for WHISPER_BATCH_SECS before processing the audio
    for i in range(RATE // CHUNK):
        transcriber.process_audio(in_data, CHUNK, time_info, 0)
    assert mock_buffer.text == ""
    transcriber.process_audio(in_data, CHUNK, time_info, 0)
    assert mock_buffer.text == "one 2"

    # Changes the non frozen text if whisper changes its mind
    transcriber.process_audio(in_data, WHISPER_BATCH_SECS * RATE, time_info, 0)
    assert mock_buffer.text == "one two three"

    # Don't process audio if we've fallen too far behind realtime
    time_info = Mock(currentTime=REAL_TIME_THRESHOLD, inputBufferAdcTime=0.0)
    transcriber.process_audio(in_data, WHISPER_BATCH_SECS * RATE, time_info, 0)
    assert mock_buffer.text == "one two three"

    transcriber.close()
