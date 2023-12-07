from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT
from mentat.vision.vision_manager import ScreenshotException


class ScreenshotCommand(Command, command_name="screenshot"):
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
                    "Using a version of gpt that doesn't support images. Changing to"
                    " gpt-4-vision-preview",
                    color="yellow",
                )
                config.model = "gpt-4-vision-preview"
        else:
            stream.send(
                "Can't determine if this model supports vision. Attempting anyway.",
                color="yellow",
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
                color="green",
            )
        except ScreenshotException:
            return  # Screenshot manager will print the error to stream.

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["url or local file"]

    @classmethod
    def help_message(cls) -> str:
        return "Opens the url or local file in chrome and takes a screenshot."
