import logging

from termcolor import cprint

from .config_manager import ConfigManager
from .mentat_prompt_session import MentatPromptSession


class UserQuitInterrupt(Exception):
    pass


class UserInputManager:
    def __init__(self, config: ConfigManager):
        self.session = MentatPromptSession(config)

    def collect_user_input(self) -> str:
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
