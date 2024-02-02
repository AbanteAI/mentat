from pathlib import Path
from typing import List

from typing_extensions import override

from mentat.command.command import Command, CommandArgument
from mentat.errors import SampleError
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path


class SampleCommand(Command, command_name="sample"):
    hidden = True  # Waiting for parse_message to be complete

    async def apply(self, *args: str) -> None:
        session_context = SESSION_CONTEXT.get()
        sampler = session_context.sampler
        stream = session_context.stream
        try:
            sample = await sampler.create_sample()
        except SampleError as e:
            stream.send(f"Failed to generate sample: {e}", style="error")
            return
        fname = f"sample_{sample.id}.json"
        if len(args) > 0:
            fpath = Path(args[0]) / fname
        else:
            samples_dir = mentat_dir_path / "samples"
            samples_dir.mkdir(exist_ok=True)
            fpath = samples_dir / fname
        sample.save(fpath)
        SESSION_CONTEXT.get().stream.send(f"Sample saved to {fpath}.", style="success")

    @override
    @classmethod
    def arguments(cls) -> List[CommandArgument]:
        return [CommandArgument("optional", "path")]

    @override
    @classmethod
    def argument_autocompletions(
        cls, arguments: list[str], argument_position: int
    ) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return "Save a sample of the current session."
