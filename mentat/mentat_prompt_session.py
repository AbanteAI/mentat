import logging
import shlex
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Set, cast

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

from .commands import Command
from .config_manager import mentat_dir_path
from .git_handler import get_non_gitignored_files

logger = logging.getLogger()


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


### TODO
# 1. get files to include autocompletions from
# 2. use pygments to generate "tokens" for each file
# 3. update completions whenever on file add/edit/delete
#   a. Recreate completion instance every time `collect_user_input` is called
#   b. Recreate completions per file on file add/edit/delete every time `collect_user_input` is called
#   c. Recreate UserInputManger (probably a bad idea) for every time user is prompted
# 4. Decide on what words to auto complete (right now it's everything)
#   a. Use ctags to add types (e.g. function, class) to completions
# 5. Use ctags if available, fallback to pygments lexer if not
# 6. Consider vscode-like fuzzy matching words with something like Fzf


class AutoCompleter(Completer):
    def __init__(self, git_root: str):
        self.git_root = git_root
        self.syntax_completions: Set[str] = set()
        self.file_name_completions: DefaultDict[str, Set[str]] = defaultdict(set)

        for git_file_path in get_non_gitignored_files(self.git_root):
            self.refresh_completions(git_file_path)

    def refresh_completions(self, file_path: str):
        """Add/edit/delete completions for some filepath"""
        try:
            with open(file_path, "r") as f:
                file_content = f.read()
        except (FileNotFoundError, NotADirectoryError):
            logging.debug(f"Skipping {file_path}. Reason: file not found")
            return
        try:
            lexer = guess_lexer_for_filename(file_path, file_content)
            lexer = cast(Lexer, lexer)
        except ClassNotFound:
            logging.debug(f"Skipping {file_path}. Reason: lexer not found")
            return

        file_name = Path(file_path).name
        self.file_name_completions[file_name].add(file_path)

        tokens = list(lexer.get_tokens(file_content))
        filtered_tokens = set()
        for token_type, token_value in tokens:
            if token_type not in Token.Name:
                continue
            if len(token_value) <= 1:
                continue
            filtered_tokens.add(token_value)
        self.syntax_completions.update(filtered_tokens)

    def get_completions(self, document: Document, _: CompleteEvent):
        """Used by `Completer` base class"""
        if document.text_before_cursor[-1] == " ":
            return
        document_words = document.text_before_cursor.split()
        if not document_words:
            return

        last_word = document_words[-1]
        get_completion_insert = lambda word: f"`{word}`"
        if last_word[0] == "`" and len(last_word) > 1:
            last_word = last_word.lstrip("`")
            get_completion_insert = lambda word: f"{word}`"

        completions = self.syntax_completions.union(set(self.file_name_completions))

        for completion in completions:
            if completion.lower().startswith(last_word.lower()):
                file_names = self.file_name_completions.get(completion)
                if file_names:
                    for file_name in file_names:
                        yield Completion(
                            get_completion_insert(file_name),
                            start_position=-len(last_word),
                            display=file_name,
                        )
                else:
                    yield Completion(
                        get_completion_insert(completion),
                        start_position=-len(last_word),
                        display=completion,
                    )


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
