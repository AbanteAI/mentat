import datetime

from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT


class SampleCommand(Command, command_name="sample"):
    async def apply(self, *args: str) -> None:
        from mentat.sample import Sample

        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        sample = await Sample.from_context(session_context)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        sample.save(f"sample_{timestamp}.json")
        stream.send("Sample saved to file.", color="light_blue")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return (
            "Generates a .json file containing complete record of current interaction"
        )
