from pathlib import Path

from mentat.command.command import Command
from mentat.errors import HistoryError
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path


class SampleCommand(Command, command_name="sample"):
    async def apply(self, *args: str) -> None:
        from mentat.sampler.sample import Sample

        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream

        try:
            sample = await Sample.from_context()
        except HistoryError as e:
            stream.send(f"Failed to generate sample: {e}", color="light_red")
            return
        fname = f"sample_{sample.id}.json"
        if len(args) > 0:
            fpath = Path(args[0]) / fname
        else:
            samples_dir = mentat_dir_path / "samples"
            samples_dir.mkdir(exist_ok=True)
            fpath = samples_dir / fname
        sample.save(str(fpath))
        SESSION_CONTEXT.get().stream.send(f"Sample saved to {fpath}.", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["path?"]

    @classmethod
    def help_message(cls) -> str:
        return "Save a sample of the current session."
