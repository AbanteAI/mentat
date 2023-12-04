import webbrowser

from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT
from mentat.transcripts import Transcript, get_transcript_logs
from mentat.utils import create_viewer


class ConversationCommand(Command, command_name="conversation"):
    hidden = True

    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        conversation = session_context.conversation

        logs = get_transcript_logs()

        viewer_path = create_viewer(
            [Transcript(timestamp="Current", messages=conversation.literal_messages)]
            + logs
        )
        webbrowser.open(f"file://{viewer_path.resolve()}")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Opens an html page showing the conversation as seen by Mentat so far"
