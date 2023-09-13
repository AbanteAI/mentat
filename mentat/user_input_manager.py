import logging

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from termcolor import cprint

from .code_context import CodeContext
from .config_manager import ConfigManager
from .mentat_prompt_session import MentatPromptSession


class FilteredFileHistory(FileHistory):
    def __init__(self, filename: str, config: ConfigManager):
        self.excluded_phrases = ["y", "n", "i", "q"]
        super().__init__(filename)

    def append_string(self, string: str):
        if string.strip().lower() not in self.excluded_phrases:
            super().append_string(string)


class UserQuitInterrupt(Exception):
    pass


class UserInputManager:
    def __init__(self, config: ConfigManager, code_context: CodeContext):
        self.mentat_session = MentatPromptSession(
            code_context,
            message=[("class:prompt", ">>> ")],
            style=Style(config.input_style()),
        )
        # Won't have suggestions, completions, commands, etc.
        self.plain_session = PromptSession[str](
            message=[("class:prompt", ">>> ")],
            style=Style(config.input_style()),
        )

    def collect_user_input(self, use_plain_session: bool = False) -> str:
        if use_plain_session:
            user_input = self.plain_session.prompt()
        else:
            user_input = self.mentat_session.prompt()
        logging.debug(f"User input:\n{user_input}")
        user_input = user_input.strip()
        if user_input.lower() == "q":
            raise UserQuitInterrupt()
        return user_input

    def ask_yes_no(self, default_yes: bool) -> bool:
        cprint("(Y/n)" if default_yes else "(y/N)")
        while (
            user_input := self.collect_user_input(use_plain_session=True).lower()
        ) not in [
            "y",
            "n",
            "",
        ]:
            cprint("(Y/n)" if default_yes else "(y/N)")
        return user_input == "y" or (user_input != "n" and default_yes)
