import logging
import os

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from termcolor import cprint

from .config_manager import ConfigManager, mentat_dir_path


class FilteredFileHistory(FileHistory):
    def __init__(self, filename: str, config: ConfigManager):
        self.excluded_phrases = ["y", "n", "i", "q"]
        super().__init__(filename)

    def append_string(self, string):
        if string.strip().lower() not in self.excluded_phrases:
            super().append_string(string)


class UserInputManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.file_history = FilteredFileHistory(
            os.path.join(mentat_dir_path, "history"), config
        )
        self.auto_suggest = AutoSuggestFromHistory()
        self.style = Style(config.input_style())
        self.prompt = [("class:prompt", ">>> ")]
        self.bindings = KeyBindings()
        self.session = PromptSession(
            message=self.prompt,
            history=self.file_history,
            auto_suggest=self.auto_suggest,
            style=self.style,
            multiline=True,
            prompt_continuation=self.prompt_continuation,
            key_bindings=self.bindings,
        )

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

    def prompt_continuation(self, width, line_number, is_soft_wrap):
        return (
            "" if is_soft_wrap else [("class:continuation", " " * (width - 2) + "> ")]
        )

    def collect_user_input(self) -> str:
        user_input = self.session.prompt().strip()
        logging.debug(f"User input:\n{user_input}")
        if user_input.lower() == "q":
            raise KeyboardInterrupt("User used 'q' to quit")
        return user_input

    def ask_yes_no(self, default_yes: bool) -> bool:
        cprint("(Y/n)" if default_yes else "(y/N)")
        while (user_input := self.collect_user_input().lower()) not in [
            "y",
            "n",
            "",
        ]:
            cprint("(Y/n)" if default_yes else "(y/N)")
        return user_input == "y" or (user_input != "n" and default_yes)
