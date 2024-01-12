import os
import shlex
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, TypedDict, cast

import attr
from pygments.lexer import Lexer
from pygments.lexers import guess_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound

from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path

SECONDS_BETWEEN_REFRESH = 5

whitespace = " \t\r\n"


class Completion(TypedDict):
    """
    Represents a single unserialized auto-completion suggestion
    """

    # The completion to add to the buffer
    content: str
    # Number of characters from the cursor the completion should be placed (negative means backwards)
    position: int
    # The display name; if not given, will default to content
    display: str | None


@attr.define
class FileCompletion:
    last_updated: datetime = attr.field()
    syntax_fragments: Set[str] = attr.field()


def get_command_filename_completions(cur_path: str) -> List[str]:
    """
    Used by commands like include, exclude, and screenshot to get filename completions.
    """
    path = Path(cur_path)

    if (
        cur_path.endswith("/")
        or cur_path.endswith(os.path.sep)
        or cur_path.endswith("~")
    ):
        actual_parent = path
        cur_file = ""
    else:
        actual_parent = path.parent
        if not path.parts:
            cur_file = ""
        else:
            cur_file = path.parts[-1]
    parent_path = actual_parent.expanduser()
    if not parent_path.is_dir():
        return []

    completions: List[str] = []
    for child_path in parent_path.iterdir():
        child_file = child_path.parts[-1]
        # is_dir = child_path.is_dir()
        if str(child_file).startswith(cur_file):
            completions.append(
                # Because prompt_toolkit doesn't start a new completion until after the user types something,
                # best UI unfortunately seems to be not having a trailing / and having the user type it.
                str(actual_parent / child_file)  # + (os.path.sep if is_dir else "")
            )

    return completions


class AutoCompleter:
    def __init__(self):
        self._all_file_completions: Set[str] = set()
        self._file_completions: Dict[Path, FileCompletion] = dict()
        self._last_refresh_at: datetime | None = None

    def _replace_last_word(
        self,
        last_word: str,
        completions: List[tuple[str, str]],
        position: int | None = None,
    ) -> List[Completion]:
        """
        Takes a list of string completions along with their displays, and filters to match only completions
        whose displays start with the last word, and then returns a list of Completions that will replace that word
        """
        filtered_completions = [
            completion
            for completion in completions
            if completion[1].startswith(last_word)
        ]
        return [
            Completion(
                content=completion[0],
                position=-len(last_word) if position is None else position,
                display=completion[1],
            )
            for completion in filtered_completions
        ]

    def _partial_shlex_split(
        self, argument_buffer: str
    ) -> tuple[List[str], bool, bool]:
        """
        Handles unescaped backslashes and unclosed quotation marks
        """

        in_quote = False
        try:
            split_buffer = shlex.split(argument_buffer)
        except ValueError as e:
            if "quotation" in str(e):
                # Try to close with a single quotation mark; if that doesn't work, close with a double quotation mark
                try:
                    split_buffer = shlex.split(argument_buffer + '"')
                except ValueError as e:
                    split_buffer = shlex.split(argument_buffer + "'")
                in_quote = True
            elif "escaped" in str(e):
                # Remove the offending backslash and pretend it isn't there
                split_buffer, in_quote, _ = self._partial_shlex_split(
                    argument_buffer[:-1]
                )
                return split_buffer, in_quote, True
            else:
                raise ValueError(f"shlex.split raised unexpected error: {e}")
        return split_buffer, in_quote, False

    def _find_shlex_last_word_position(
        self, argument_buffer: str, num_words: int
    ) -> int:
        """
        Find where the last word starts in a shlexed buffer
        """
        lex = shlex.shlex(argument_buffer, posix=True)
        lex.whitespace_split = True
        for _ in range(num_words - 1):
            lex.get_token()
        remaining = list(lex.instream)
        return 0 if not remaining else -len(remaining[0])

    def _command_argument_completion(self, buffer: str) -> List[Completion]:
        if any(buffer.startswith(space) for space in whitespace):
            return []
        if not any(space in buffer for space in whitespace):
            return self._replace_last_word(
                buffer, [(name, name) for name in Command.get_command_names()]
            )
        else:
            command_cls = Command.create_command(buffer.split()[0]).__class__
            argument_buffer = buffer.split(maxsplit=1)
            if len(argument_buffer) < 2:
                argument_buffer = ""
            else:
                argument_buffer = argument_buffer[1]

            # shlex fails if there are uncompleted quotations or backslashes not escaping anything;
            # we check for this and try to complete the quotations/backslashes, so that we can get the
            # actual escaped last_word argument to compare against our possible completions.
            split_buffer, in_quote, unescaped = self._partial_shlex_split(
                argument_buffer
            )
            last_word_position = self._find_shlex_last_word_position(
                argument_buffer, len(split_buffer)
            )

            # If we removed an ending \ and before it was whitespace, we need to move on one argument
            if unescaped and buffer[-2] in whitespace:
                split_buffer.append("")

            # shlex.split doesn't count the ending space
            if buffer[-1] in whitespace and not in_quote:
                split_buffer.append("")
                last_word_position = 0
            arg_position = len(split_buffer) - 1

            arg_completions = [
                (shlex.quote(name), name)
                for name in command_cls.argument_autocompletions(
                    split_buffer, arg_position
                )
            ]
            return self._replace_last_word(
                split_buffer[-1], arg_completions, last_word_position
            )

    def _refresh_file_completion(self, file_path: Path):
        if not file_path.exists() or file_path.is_dir():
            if file_path in self._file_completions:
                del self._file_completions[file_path]
            return
        with open(file_path, "r") as f:
            file_content = f.read()

        try:
            lexer = cast(Lexer, guess_lexer_for_filename(file_path, file_content))
        except ClassNotFound:
            self._file_completions[file_path] = FileCompletion(datetime.utcnow(), set())
            return

        tokens = list(lexer.get_tokens(file_content))
        filtered_tokens = set[str]()
        for token_type, token_value in tokens:
            if token_type not in Token.Name:
                continue
            if len(token_value) <= 1:
                continue
            filtered_tokens.add(token_value)
        self._file_completions[file_path] = FileCompletion(
            datetime.utcnow(), filtered_tokens
        )

    def _refresh_all_file_completions(self):
        ctx = SESSION_CONTEXT.get()

        file_paths = ctx.code_context.include_files.keys()

        # Remove syntax completions for files not in the context
        for file_path in set(self._file_completions.keys()):
            if file_path not in file_paths:
                del self._file_completions[file_path]

        # Add/update syntax completions for files in the context
        for file_path in file_paths:
            if file_path not in self._file_completions:
                self._refresh_file_completion(file_path)
            else:
                modified_at = datetime.utcfromtimestamp(os.path.getmtime(file_path))
                if self._file_completions[file_path].last_updated < modified_at:
                    self._refresh_file_completion(file_path)

        # Build de-duped syntax completions
        self._all_file_completions = set[str]()
        for file_path, file_completion in self._file_completions.items():
            rel_path = get_relative_path(file_path, ctx.cwd)
            self._all_file_completions.add(str(rel_path))
            self._all_file_completions.update(file_completion.syntax_fragments)

        self._last_refresh_at = datetime.utcnow()

    def get_file_completions(self, buffer: str) -> List[Completion]:
        if (
            self._last_refresh_at is None
            or (datetime.utcnow() - self._last_refresh_at).seconds
            > SECONDS_BETWEEN_REFRESH
        ):
            self._refresh_all_file_completions()

        if not buffer or buffer[-1] == " ":
            return []

        words = buffer.split()
        if not words:
            return []

        last_word = words[-1]
        position = -len(last_word)
        if last_word.startswith("`"):
            last_word = last_word[1:]

        completions = [
            (f"`{completion}`", completion) for completion in self._all_file_completions
        ]
        return self._replace_last_word(last_word, completions, position)

    def get_completions(
        self, buffer: str, command_autocomplete: bool = False
    ) -> List[Completion]:
        """
        Get the auto-completion suggestions for the current user buffer.
        """
        if not buffer.strip():
            return []

        if buffer.startswith("/") and command_autocomplete:
            return self._command_argument_completion(buffer[1:])
        else:
            return self.get_file_completions(buffer)
