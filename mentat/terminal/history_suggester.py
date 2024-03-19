from pathlib import Path

from git import Optional
from textual.suggester import Suggester
from typing_extensions import override


class HistorySuggester(Suggester):
    def __init__(self, history_file: Path, *, case_sensitive: bool = True) -> None:
        self.history_file = history_file
        self.position = -1
        if not history_file.exists():
            with open(self.history_file, "w") as f:
                pass
        with open(self.history_file, "r") as f:
            self._suggestions = f.read().split("\n")
        super().__init__(use_cache=False, case_sensitive=case_sensitive)

    def append_to_history(self, submission: str):
        self.position = 0
        if not submission.strip() or (self._suggestions and self._suggestions[-1] == submission):
            return
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

    def move_up(self) -> Optional[str]:
        if self.position == -len(self._suggestions):
            return None
        self.position -= 1
        return self._suggestions[self.position]

    def move_down(self) -> Optional[str]:
        if self.position == -1:
            return None
        self.position += 1
        return self._suggestions[self.position]

    # This is a bit of a hacky way to let the autocomplete (which watches the input value)
    # know if the new input value was from moving in history (in which case we don't want autocomplete to pop up)
    def just_moved(self, value: str):
        return self._suggestions[self.position] == value
