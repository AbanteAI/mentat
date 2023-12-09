from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT


class SampleCommand(Command, command_name="sample"):
    async def apply(self, *args: str) -> None:
        from mentat.sampler.sample import Sample

        sample = await Sample.from_context()
        fname = f"sample_{sample.hexsha_edit}.json"
        sample.save(fname)
        SESSION_CONTEXT.get().stream.send(f"Sample saved to {fname}.", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Undo the last change made by Mentat"
