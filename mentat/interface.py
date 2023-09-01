from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Dict, Iterable, Optional

# from .config_manager import ConfigManager  # circular import; using Forward Declarations instead
from .streaming_printer import StreamingPrinter


class InterfaceType(Enum):
    Terminal = "terminal"
    VSCode = "vscode"


def initialize_mentat_interface(
    interface_type: InterfaceType,
):
    match interface_type:
        case InterfaceType.Terminal:
            return TerminalMentatInterface()
        # case InterfaceType.VSCode:
        #     from .vscode_interface import VSCodeMentatInterface
        #     return VSCodeMentatInterface()


class MentatInterface(ABC):
    config: Optional['ConfigManager']

    def register_config(self, config: 'ConfigManager'):
        """Required to initialize UserInputManager with Autocomplete"""
        self.config = config

    @abstractmethod
    def display(
        self,
        content: str,
        color: Optional[str] = None,
        end: Optional[str] = "\n",
    ) -> None:
        """Handle displaying output to user."""
        raise NotImplementedError('display() not implemented')

    def get_streaming_printer(self) -> StreamingPrinter:
        """Return a streaming printer."""
        raise NotImplementedError('get_streaming_printer() not implemented')

    def get_user_input(
        self, 
        prompt=None, 
        options=None
    ) -> str:
        """Handle getting input from user."""
        raise NotImplementedError('get_user_input() not implemented')

    def ask_yes_no(
        self, 
        prompt=None,
        default_yes: bool=True
    ) -> bool:
        """Handle getting yes/no input from user."""
        return self.get_user_input(prompt, options=["y", "n"]).lower() == "y"

    @abstractmethod
    def exit(self):
        """Handle cleanup or exit procedures."""
        pass

# ------------------
# Terminal Interface
# ------------------

from termcolor import cprint, colored
from .user_input_manager import UserInputManager
from .config_manager import ConfigManager

class TerminalStreamingPrinter(StreamingPrinter):
    def add_string(self, string, end="\n", color=None):
        if len(string) == 0:
            return
        string += end

        colored_string = colored(string, color) if color is not None else string

        index = colored_string.index(string)
        characters = list(string)
        characters[0] = colored_string[:index] + characters[0]
        characters[-1] = characters[-1] + colored_string[index + len(string) :]

        self.strings_to_print.extend(characters)
        self.chars_remaining += len(characters)


class TerminalMentatInterface(MentatInterface):
    
    def register_config(self, config: ConfigManager):
        self.ui = UserInputManager(config)

    def get_user_input(        
        self, 
        prompt: str=None, 
        options: Optional[Iterable[str]]=None
    ) -> str:
        while True:
            if prompt is not None:
                if options is None:
                    self.display(prompt)
                else:                
                    self.display(f"{prompt} ({'/'.join(options)})")
            user_input = self.ui.session.prompt().strip()
            if options is None:
                return user_input
            elif user_input.lower() in options:
                return user_input
            else:
                self.display("Invalid response")

    def display(self, content, color=None, end="\n"):
        if color:
            cprint(content, color=color, end=end)
        else:
            print(content, end=end, flush=True)

    def get_streaming_printer(self):
        printer = TerminalStreamingPrinter(self)
        return printer

    def exit(self):
        exit()
