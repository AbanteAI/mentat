from pathlib import Path

from mentat.command.command import Command
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import mentat_dir_path


class SampleCommand(Command, command_name="sample"):
    async def apply(self, *args: str) -> None:
        from mentat.sampler.sample import Sample

        sample = await Sample.from_context()
        fname = f"sample_{sample.hexsha_edit}.json"
        if len(args) > 0:
            fpath = Path(args[0]) / fname
        else:
            samples_dir = mentat_dir_path / "samples"
            samples_dir.mkdir(exist_ok=True)
            fpath = samples_dir / fname
        sample.save(str(fpath))
        SESSION_CONTEXT.get().stream.send(f"Sample saved to {fname}.", color="green")

    @classmethod
    def argument_names(cls) -> list[str]:
        return ["path?"]

    @classmethod
    def help_message(cls) -> str:
        return "Undo the last change made by Mentat"
