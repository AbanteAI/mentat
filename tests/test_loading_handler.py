from datetime import datetime
from uuid import uuid4

from mentat.session_stream import StreamMessage, StreamMessageSource
from mentat.terminal.loading import LoadingHandler


class MockTqdm:
    total = 100
    n = 0

    def __init__(self, desc):
        self.desc = desc

    def update(self, n):
        self.n += n

    def set_description(self, desc):
        self.desc = desc

    closed = False

    def close(self):
        self.closed = True


def test_loading_handler(mocker):
    mock_tqdm = MockTqdm("")
    tqdm_mock = mocker.patch("mentat.terminal.loading.tqdm")
    tqdm_mock.return_value = mock_tqdm
    lh = LoadingHandler()

    msg = StreamMessage(
        uuid4(),
        "loading",
        StreamMessageSource.SERVER,
        "Test message",
        {"progress": 50},
        datetime.utcnow(),
    )
    lh.update(msg)
    assert mock_tqdm.n == 50
    assert mock_tqdm.closed is False

    lh.update(msg)
    assert mock_tqdm.n == 100
    assert mock_tqdm.desc == "Test message"
    assert mock_tqdm.closed is True
