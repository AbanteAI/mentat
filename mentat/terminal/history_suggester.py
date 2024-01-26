from pathlib import Path

from textual.suggester import Suggester
from typing_extensions import override


class HistorySuggester(Suggester):
    def __init__(self, history_file: Path, *, case_sensitive: bool = True) -> None:
        self.history_file = history_file
        if not history_file.exists():
            with open(self.history_file, "w") as f:
                pass
        with open(self.history_file, "r") as f:
            self._suggestions = f.read().split("\n")
        super().__init__(use_cache=False, case_sensitive=case_sensitive)

    def append_to_history(self, submission: str):
        self._suggestions.append(submission)
        with open(self.history_file, "a") as f:
            f.write(f"{submission}\n")

    @override
    async def get_suggestion(self, value: str) -> str | None:
        for suggestion in reversed(self._suggestions):
            if not self.case_sensitive:
                suggestion = suggestion.casefold()
                value = value.casefold()
            if suggestion.startswith(value):
                return suggestion
        return None
