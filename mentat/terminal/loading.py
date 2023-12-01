from tqdm import tqdm

from mentat.session_stream import StreamMessage


class LoadingHandler:
    def __init__(self):
        self.pbar = None

    def update(self, message: StreamMessage):
        """Create or update a loading bar with text and progress value (0-100)"""

        terminate = bool(message.extra and message.extra.get("terminate"))
        if self.pbar is None and terminate:
            self.terminate()
            return

        text = "" if not isinstance(message.data, str) else message.data
        if self.pbar is None:
            self.pbar = tqdm(
                total=100,
                desc=text,
                bar_format="{percentage:3.0f}%|{bar:50}| {desc}",
            )
        elif text:
            self.pbar.set_description(text)

        if "progress" in message.extra:
            _progress = min(message.extra["progress"], self.pbar.total - self.pbar.n)
            self.pbar.update(_progress)

        if terminate or self.pbar.n == self.pbar.total:
            self.terminate()

    def terminate(self, message: str | None = None):
        if self.pbar is not None:
            if message is not None:
                self.pbar.set_description(message)
            if self.pbar.total > self.pbar.n:
                self.pbar.update(self.pbar.total - self.pbar.n)
            self.pbar.close()
            self.pbar = None
