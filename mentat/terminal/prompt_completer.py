from typing import Iterable, List

from prompt_toolkit.completion import CompleteEvent, Completer
from prompt_toolkit.completion import Completion as PromptToolkitCompletion
from prompt_toolkit.document import Document

from mentat.auto_completer import Completion
from mentat.session_stream import SessionStream, StreamMessageSource


class MentatCompleter(Completer):
    def __init__(self, stream: SessionStream):
        self.stream = stream
        self.command_autocomplete = False

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[PromptToolkitCompletion]:
        raise NotImplementedError

    async def get_completions_async(
        self, document: Document, complete_event: CompleteEvent
    ):
        text = document.text_before_cursor
        message = self.stream.send(
            text,
            source=StreamMessageSource.CLIENT,
            channel="completion_request",
            command_autocomplete=self.command_autocomplete,
        )

        response = await self.stream.recv(channel=f"completion_request:{message.id}")
        completions: List[Completion] = response.data
        for completion in completions:
            yield PromptToolkitCompletion(
                text=completion["content"],
                start_position=completion["position"],
                display=completion["display"],
            )
