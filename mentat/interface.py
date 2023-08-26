from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Dict, Iterable, Optional

from termcolor import cprint

_interface_instance = None


def get_interface() -> MentatInterface:
    if _interface_instance is None:
        raise Exception("Mentat interface not initialized")
    return _interface_instance


# convenience function for common interaction
def output(content: str, color: str):
    get_interface().interact(content=content, color=color)


class InterfaceType(Enum):
    Terminal = "terminal"
    VSCode = "vscode"


def initialize_mentat_interface(
    interface_type: InterfaceType,
    interaction_callback: Optional[Callable[[Dict], str]] = None,
):
    global _interface_instance

    # should only be initizalized once
    assert _interface_instance is None

    # callback provided iff interface_type is VSCode
    assert (interface_type == InterfaceType.VSCode) == (
        interaction_callback is not None
    )

    match interface_type:
        case InterfaceType.Terminal:
            _interface_instance = TerminalMentatInterface()
        case InterfaceType.VSCode:
            _interface_instance = VSCodeMentatInterface(interaction_callback)


class MentatInterface(ABC):
    @abstractmethod
    def interact(
        self,
        content: Optional[str] = None,
        color: Optional[str] = None,
        is_error: Optional[bool] = False,
        return_user_input: Optional[bool] = False,
        user_input_options: Optional[Iterable[str]] = None,
    ) -> str:
        """Handle both receiving input and sending output using the provided callback."""
        pass

    @abstractmethod
    def interrupt(self):
        """Handle user interruptions."""
        pass

    @abstractmethod
    def exit(self):
        """Handle cleanup or exit procedures."""
        pass


class TerminalMentatInterface(MentatInterface):
    def interact(
        self,
        content: Optional[str] = None,
        color: Optional[str] = None,
        is_error: Optional[bool] = False,
        return_user_input: Optional[bool] = False,
        user_input_options: Optional[Iterable[str]] = None,
    ) -> str:
        if content:
            if color:
                cprint(content, color=color)
            else:
                print(content)
        if return_user_input:
            # get and return user input
            pass

    def interrupt(self):
        pass

    def exit(self):
        pass


class VSCodeMentatInterface(MentatInterface):
    def __init__(self, interaction_callback: Callable):
        self.interaction_callback = interaction_callback

    def interact(
        self,
        content: Optional[str] = None,
        color: Optional[str] = None,
        is_error: Optional[bool] = False,
        return_user_input: Optional[bool] = False,
        user_input_options: Optional[Iterable[str]] = None,
    ) -> str:
        """Handle both receiving input and sending output using the provided callback."""
        return self.interaction_callback(
            content=content,
            color=color,
            is_error=is_error,
            return_user_input=return_user_input,
            user_input_options=user_input_options,
        )

    def interrupt(self):
        pass

    def exit(self):
        pass
