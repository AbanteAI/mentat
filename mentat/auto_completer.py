import shlex
from typing import List, TypedDict

from mentat.command.command import Command


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


whitespace = " \t\r\n"


def _replace_last_word(
    last_word: str, completions: List[tuple[str, str]], position: int | None = None
) -> List[Completion]:
    """
    Takes a list of string completions along with their displays, and filters to match only completions
    whose displays start with the last word, and then returns a list of Completions that will replace that word
    """
    filtered_completions = [
        completion for completion in completions if completion[1].startswith(last_word)
    ]
    return [
        Completion(
            content=completion[0],
            position=-len(last_word) if position is None else position,
            display=completion[1],
        )
        for completion in filtered_completions
    ]


def _partial_shlex_split(argument_buffer: str) -> tuple[List[str], bool]:
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
            return _partial_shlex_split(argument_buffer[:-1])
        else:
            raise ValueError(f"shlex.split raised unexpected error: {e}")
    return split_buffer, in_quote


def _find_shlex_last_word_position(argument_buffer: str, num_words: int) -> int:
    """
    Find where the last word starts in a shlexed buffer
    """
    lex = shlex.shlex(argument_buffer, posix=True)
    lex.whitespace_split = True
    for _ in range(num_words - 1):
        lex.get_token()
    remaining = list(lex.instream)
    return 0 if not remaining else -len(remaining[0])


def _command_argument_completion(buffer: str) -> List[Completion]:
    if " " not in buffer:
        return _replace_last_word(
            buffer, [(name, name) for name in Command.get_command_names()]
        )
    else:
        command = Command.create_command(buffer.split(" ")[0])
        argument_buffer = " ".join(buffer.split(" ")[1:])

        # shlex fails if there are uncompleted quotations or backslashes not escaping anything;
        # we check for this and try to complete the quotations/backslashes, so that we can get the
        # actual escaped last_word argument to compare against our possible completions.
        split_buffer, in_quote = _partial_shlex_split(argument_buffer)
        last_word_position = _find_shlex_last_word_position(
            argument_buffer, len(split_buffer)
        )

        # shlex.split doesn't count the ending space
        if buffer[-1] in whitespace and not in_quote:
            split_buffer.append("")
            last_word_position = 0
        arg_position = len(split_buffer) - 1

        arg_completions = [
            (shlex.quote(name), name)
            for name in command.argument_autocompletions(
                split_buffer[:-1], arg_position
            )
        ]
        return _replace_last_word(split_buffer[-1], arg_completions, last_word_position)


def get_completions(buffer: str) -> List[Completion]:
    """
    Get the auto-completion suggestions for the current user buffer.
    """
    if not buffer.strip():
        return []

    if buffer.startswith("/"):
        return _command_argument_completion(buffer[1:])

    # TODO: Function, class, and filename completion
    return []


"""
        self.syntax_completions: Dict[Path, SyntaxCompletion] = dict()
        self.file_name_completions: DefaultDict[str, Set[Path]] = defaultdict(set)
        self.command_completer = WordCompleter(
            words=Command.get_command_completions(),
            ignore_case=True,
            sentence=True,
        )

        self._all_syntax_words: Set[str] = set()
        self._last_refresh_at: datetime | None = None

    def refresh_completions_for_file_path(self, file_path: Path):

        session_context = SESSION_CONTEXT.get()

        file_path = session_context.cwd / file_path

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

        self.file_name_completions[file_path.name].add(file_path)

        tokens = list(lexer.get_tokens(file_content))
        filtered_tokens = set[str]()
        for token_type, token_value in tokens:
            if token_type not in Token.Name:
                continue
            if len(token_value) <= 1:
                continue
            filtered_tokens.add(token_value)
        self.syntax_completions[file_path] = SyntaxCompletion(words=filtered_tokens)

    async def refresh_completions(self):
        # TODO: The client shouldn't really be using SESSION_CONTEXT;
        # clients other than the TerminalClient won't be able to;
        # should we send this information via the stream?
        session_context = SESSION_CONTEXT.get()
        code_context = session_context.code_context

        file_paths = code_context.include_files.keys()

        # Remove syntax completions for files not in the context
        for file_path in set(self.syntax_completions.keys()):
            if file_path not in file_paths:
                del self.syntax_completions[file_path]
                file_name = file_path.name
                self.file_name_completions[file_name].remove(file_path)
                if len(self.file_name_completions[file_name]) == 0:
                    del self.file_name_completions[file_name]

        # Add/update syntax completions for files in the context
        for file_path in file_paths:
            if file_path not in self.syntax_completions:
                self.refresh_completions_for_file_path(file_path)
            else:
                modified_at = datetime.utcfromtimestamp(os.path.getmtime(file_path))
                if self.syntax_completions[file_path].created_at < modified_at:
                    self.refresh_completions_for_file_path(file_path)

        # Build de-duped syntax completions
        _all_syntax_words = set[str]()
        for syntax_completion in self.syntax_completions.values():
            _all_syntax_words.update(syntax_completion.words)
        self._all_syntax_words = _all_syntax_words

        self._last_refresh_at = datetime.utcnow()

    def get_completions(  # pyright: ignore
        self, document: Document, complete_event: CompleteEvent
    ):
        raise NotImplementedError

    async def get_completions_async(
        self, document: Document, complete_event: CompleteEvent
    ):
        if document.text_before_cursor == "":
            return
        if (
            self._last_refresh_at is None
            or (datetime.utcnow() - self._last_refresh_at).seconds > 5
        ):
            await self.refresh_completions()
        if (
            document.text_before_cursor[0] == "/"
            and not document.text_before_cursor[-1].isspace()
        ):
            command_completions = self.command_completer.get_completions(
                document, complete_event
            )
            for completion in command_completions:
                yield completion

        if document.text_before_cursor[-1] == " ":
            return
        document_words = document.text_before_cursor.split()
        if not document_words:
            return

        last_word = document_words[-1]
        get_completion_insert: Callable[[str], str] = lambda word: f"`{word}`"
        if last_word[0] == "`" and len(last_word) > 1:
            last_word = last_word.lstrip("`")
            get_completion_insert: Callable[[str], str] = lambda word: f"{word}`"

        completions = self._all_syntax_words.union(set(self.file_name_completions))

        for completion in completions:
            if completion.lower().startswith(last_word.lower()):
                file_names = self.file_name_completions.get(completion)
                if file_names:
                    for file_name in file_names:
                        yield Completion(
                            get_completion_insert(str(file_name)),
                            start_position=-len(last_word),
                            display=str(file_name),
                        )
                else:
                    yield Completion(
                        get_completion_insert(completion),
                        start_position=-len(last_word),
                        display=completion,
                    )
"""
