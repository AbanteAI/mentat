from typing import List

from typing_extensions import override

from mentat.auto_completer import get_command_filename_completions
from mentat.command.command import Command, CommandArgument
from mentat.session_context import SESSION_CONTEXT
from mentat.vision.vision_manager import ScreenshotException


class ScreenshotCommand(Command, command_name="screenshot"):
    @override
    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        vision_manager = session_context.vision_manager
        stream = session_context.stream
        config = session_context.config
        conversation = session_context.conversation
        model = config.model

        if "gpt" in model:
            if "vision" not in model:
                stream.send(
                    "Using a version of gpt that doesn't support images. Changing to" " gpt-4-vision-preview",
                    style="warning",
                )
                config.model = "gpt-4-vision-preview"
        else:
            stream.send(
                "Can't determine if this model supports vision. Attempting anyway.",
                style="warning",
            )

        try:
            image = vision_manager.screenshot(*args)

            if len(args) == 0:
                path = "the current screen"
            else:
                path = args[0]
            conversation.add_user_message(f"A screenshot of {path}", image=image)
            stream.send(
                f"Screenshot taken for: {path}.",
                style="success",
            )
        except ScreenshotException:
            return  # Screenshot manager will print the error to stream.

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("optional", ["path", "url"])]

    @override
    @classmethod
    def argument_autocompletions(cls, arguments: list[str], argument_position: int) -> list[str]:
        return get_command_filename_completions(arguments[-1])

    @override
    @classmethod
    def help_message(cls) -> str:
        return "Open a url or local file in a web browser and take a screenshot."
