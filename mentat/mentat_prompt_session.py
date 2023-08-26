import shlex

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory, Suggestion
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion.word_completer import WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent

from .commands import Command
from .config_manager import mentat_dir_path


class FilteredFileHistory(FileHistory):
    def __init__(self, filename: str):
        self.excluded_phrases = ["y", "n", "i", "q"]
        super().__init__(filename)

    def append_string(self, string):
        if (
            string.strip().lower() not in self.excluded_phrases
            # If the user mistypes a command, we don't want it to appear later
            and string.strip()
            and string.strip()[0] != "/"
        ):
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


class MentatPromptSession(PromptSession):
    def __init__(self, *args, **kwargs):
        self._setup_bindings()
        super().__init__(
            completer=WordCompleter(
                words=Command.get_command_completions(),
                ignore_case=True,
                sentence=True,
            ),
            history=FilteredFileHistory(mentat_dir_path / "history"),
            auto_suggest=FilteredHistorySuggestions(),
            multiline=True,
            prompt_continuation=self.prompt_continuation,
            key_bindings=self.bindings,
            *args,
            **kwargs,
        )

    def prompt(self, *args, **kwargs):
        # Automatically capture all commands
        while (user_input := super().prompt(*args, **kwargs)).startswith("/"):
            arguments = shlex.split(user_input[1:])
            command = Command.create_command(arguments[0])
            command.apply(*arguments[1:])
        return user_input

    def prompt_continuation(self, width, line_number, is_soft_wrap):
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
                and app.current_buffer.text
                and app.current_buffer.text[0] != "/"
            )

        # c-i is the code for tab
        @self.bindings.add("c-i", filter=complete_suggestion)
        def _(event: KeyPressEvent):
            suggestion = event.current_buffer.suggestion
            if suggestion:
                event.current_buffer.insert_text(suggestion.text)
