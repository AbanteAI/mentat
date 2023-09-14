import logging
import os
import shlex
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import DefaultDict, Dict, Set, cast

from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory, Suggestion
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.completion.word_completer import WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from pygments.lexer import Lexer
from pygments.lexers import guess_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound

from mentat.engine import MentatEngine

from .prompt_completer import MentatCompleter


class MentatPromptSession(PromptSession):
    def __init__(self, engine: MentatEngine, *args, **kwargs):
        self.engine = engine

        self._setup_bindings()
        super().__init__(
            # completer=MentatCompleter(self.engine),
            # history=FilteredFileHistory(mentat_dir_path / "history"),
            # auto_suggest=FilteredHistorySuggestions(),
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

        @self.bindings.add("right", filter=complete_suggestion)
        def _(event: KeyPressEvent):
            suggestion = event.current_buffer.suggestion
            if suggestion:
                event.current_buffer.insert_text(suggestion.text)

        @self.bindings.add("c-c")
        def _(event: KeyPressEvent):
            if event.current_buffer.text != "":
                event.current_buffer.reset()
            else:
                event.app.exit(result="q")
