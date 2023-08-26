import logging
import sys
from pathlib import Path
from typing import Set, cast

from ipdb import set_trace
from prompt_toolkit import PromptSession
from prompt_toolkit.application.current import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from pygments.lexer import Lexer
from pygments.lexers import guess_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound
from termcolor import cprint

from .config_manager import ConfigManager, mentat_dir_path
from .git_handler import get_non_gitignored_files
from .logging_config import setup_logging

# setup_logging()
#
# logger = logging.getLogger()
# stream_handler = logging.StreamHandler()
# stream_handler.setLevel(logging.DEBUG)
# logger.addHandler(stream_handler)


class FilteredFileHistory(FileHistory):
    def __init__(self, filename: str, config: ConfigManager):
        self.excluded_phrases = ["y", "n", "i", "q"]
        super().__init__(filename)

    def append_string(self, string):
        if string.strip().lower() not in self.excluded_phrases:
            super().append_string(string)


### TODO
# 1. get files to include autocompletions from
# 2. use pygments to generate "tokens" for each file
# 3. update completions whenever on file add/edit/delete
#   a. Recreate completion instance every time `collect_user_input` is called
#   b. Recreate completions per file on file add/edit/delete every time `collect_user_input` is called
#   c. Recreate UserInputManger (probably a bad idea) for every time user is prompted
# 4. Decide on what words to auto complete (right now it's everything)
#   a. Use ctags to add types (e.g. function, class) to completions


class AutoCompleter(Completer):
    def __init__(self, git_root: str):
        self.git_root = git_root
        self.words: Set[str] = set()

        git_file_paths = get_non_gitignored_files(self.git_root)
        for git_file_path in git_file_paths:
            abs_git_file_path = Path(self.git_root).joinpath(git_file_path)
            try:
                with open(abs_git_file_path, "r") as f:
                    git_file_content = f.read()
            except (FileNotFoundError, NotADirectoryError):
                logging.debug(f"Skipping {git_file_path}. Reason: file not found")
                continue
            try:
                lexer = guess_lexer_for_filename(git_file_path, git_file_content)
                lexer = cast(Lexer, lexer)
            except ClassNotFound:
                logging.debug(f"Skipping {git_file_path}. Reason: lexer not found")
                continue
            tokens = list(lexer.get_tokens(git_file_content))
            self.words.update(token[1] for token in tokens if token[0] in Token.Name)

    def get_completions(self, document: Document, _: CompleteEvent):
        """Used by `Completer` base class"""
        document_words = document.text_before_cursor.split()
        if not document_words:
            return

        last_word = document_words[-1]
        get_word_insert = lambda word: f"`{word}`"
        if last_word[0] == "`" and len(last_word) > 1:
            last_word = last_word.lstrip("`")
            get_word_insert = lambda word: f"{word}`"

        for word in self.words:
            if word.lower().startswith(last_word.lower()):
                yield Completion(
                    get_word_insert(word), start_position=-len(last_word), display=word
                )

    def refresh_completions(self, file_path: str):
        """Add/edit/delete completions for some filepath"""


class UserQuitInterrupt(Exception):
    pass


class UserInputManager:
    def __init__(self, config: ConfigManager, git_root: str):
        self.config = config
        self.git_root = git_root
        self.file_history = FilteredFileHistory(mentat_dir_path / "history", config)
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
        self.session.completer = AutoCompleter(git_root=self.git_root)
        user_input = self.session.prompt().strip()
        logging.debug(f"User input:\n{user_input}")
        if user_input.lower() == "q":
            raise UserQuitInterrupt()
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
