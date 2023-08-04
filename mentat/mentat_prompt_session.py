import os

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from .config_manager import ConfigManager, mentat_dir_path


class FilteredFileHistory(FileHistory):
    def __init__(self, filename: str):
        self.excluded_phrases = ["y", "n", "i", "q"]
        super().__init__(filename)

    def append_string(self, string):
        if string.strip().lower() not in self.excluded_phrases:
            super().append_string(string)


class MentatPromptSession(PromptSession):
    def __init__(self, config: ConfigManager):
        self.file_history = FilteredFileHistory(
            os.path.join(mentat_dir_path, "history")
        )
        self.auto_suggest = AutoSuggestFromHistory()
        self.style = Style(config.input_style())
        self._setup_bindings()
        super().__init__(
            message=[("class:prompt", ">>> ")],
            history=self.file_history,
            auto_suggest=self.auto_suggest,
            style=self.style,
            multiline=True,
            prompt_continuation=self.prompt_continuation,
            key_bindings=self.bindings,
            # Toolbar automatically gets the class bottom-toolbar, and the text gets the class bottom-toolbar.text
            # Also, fg and bg are automatically reversed for the bottom toolbar (adding noreverse will undo this)
            bottom_toolbar="",
        )

    def prompt_continuation(self, width, line_number, is_soft_wrap):
        return (
            "" if is_soft_wrap else [("class:continuation", " " * (width - 2) + "> ")]
        )

    def _setup_bindings(self):
        self.bindings = KeyBindings()

        @self.bindings.add("s-down")
        @self.bindings.add("c-j")
        def _(event):
            event.current_buffer.insert_text("\n")

        @self.bindings.add("enter")
        def _(event):
            event.current_buffer.validate_and_handle()

        @Condition
        def suggestion_available() -> bool:
            app = get_app()
            return (
                app.current_buffer.suggestion is not None
                and len(app.current_buffer.suggestion.text) > 0
                and app.current_buffer.document.is_cursor_at_the_end
            )

        # c-i is the code for tab
        @self.bindings.add("c-i", filter=suggestion_available)
        def _(event):
            suggestion = event.current_buffer.suggestion
            if suggestion:
                event.current_buffer.insert_text(suggestion.text)

        @self.bindings.add("escape")
        def _(event):
            pass
