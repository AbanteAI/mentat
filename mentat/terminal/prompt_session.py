from typing import Any

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

    def prompt_continuation(
        self, width: int, line_number: int, is_soft_wrap: int
    ) -> AnyFormattedText:
        return (
            "" if is_soft_wrap else [("class:continuation", " " * (width - 2) + "> ")]
        )

    def _setup_bindings(self):
        self.bindings = KeyBindings()

        @Condition
        def not_searching() -> bool:
            return not get_app().layout.is_searching

        @self.bindings.add("s-down", filter=not_searching)
        @self.bindings.add("c-j", filter=not_searching)
        def _(event: KeyPressEvent):
            event.current_buffer.insert_text("\n")

        @self.bindings.add("enter", filter=not_searching)
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

        @self.bindings.add("c-c", filter=not_searching)
        @self.bindings.add("c-d", filter=not_searching)
        def _(event: KeyPressEvent):
            if event.current_buffer.text != "":
                event.current_buffer.reset()
            else:
                event.app.exit(result="q")
