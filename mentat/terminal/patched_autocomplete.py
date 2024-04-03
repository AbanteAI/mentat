from dataclasses import dataclass
from typing import List

from textual import events
from textual_autocomplete import AutoComplete, Dropdown, DropdownItem
from typing_extensions import override

from mentat.auto_completer import Completion
from mentat.session_stream import SessionStream, StreamMessageSource
from mentat.terminal.history_suggester import HistorySuggester


class PatchedAutoComplete(AutoComplete):
    """
    We want more fine control over replacing the text when a completion is
    selected, so we patch _select_item.
    """

    @override
    def _select_item(self):
        selected: CompletionDropdownItem | None = self.dropdown.selected_item  # pyright: ignore
        if self.dropdown.display and selected is not None:
            cursor_position: int = self.input.cursor_position  # pyright: ignore
            before = self.input.value[: cursor_position + selected.position]
            after = self.input.value[cursor_position:]
            self.input.value = before + selected.content + after
            self.input.cursor_position = cursor_position + selected.position + len(selected.content)

            self.dropdown.display = False
            self.post_message(self.Selected(item=selected))


@dataclass
class CompletionDropdownItem(DropdownItem):
    """
    A dropdown item with a full completion to carry all of the information we need
    """

    content: str = ""
    position: int = 0


class PatchedDropdown(Dropdown):
    """
    The dropdown class in textual_autocomplete isn't able to do everything we need it to (mainly async completions),
    so this class patchs some of its methods to add the functionality we need.
    """

    @override
    def __init__(
        self,
        stream: SessionStream,
        history_suggestor: HistorySuggester,
        id: str | None = None,
        classes: str | None = None,
    ):
        self.stream = stream
        self.history_suggester = history_suggestor
        super().__init__([], id, classes)

    # This function is mostly copied from Dropdown; the only change is using our async functions as callbacks
    @override
    def on_mount(self, event: events.Mount) -> None:
        screen_layers = list(self.screen.styles.layers)
        if "textual-autocomplete" not in screen_layers:
            screen_layers.append("textual-autocomplete")

        self.screen.styles.layers = tuple(screen_layers)  # type: ignore

        self.watch(
            self.input_widget,
            attribute_name="value",
            callback=self._async_input_value_changed,  # Changed
        )

        self.watch(
            self.input_widget,
            attribute_name="cursor_position",
            callback=self._async_input_cursor_position_changed,  # Changed
        )

        self.watch(
            self.screen,
            attribute_name="scroll_target_y",
            callback=self.handle_screen_scroll,
        )

        if self.input_widget is not None:  # pyright: ignore
            self.sync_state(
                self.input_widget.value,
                self.input_widget.cursor_position,  # pyright: ignore
            )

    async def _get_completions(self) -> List[DropdownItem]:
        text = self.input_widget.value[
            : self.input_widget.cursor_position  # pyright: ignore
        ]
        message = self.stream.send(
            text,
            source=StreamMessageSource.CLIENT,
            channel="completion_request",
            command_autocomplete=self.parent.parent.command_autocomplete,  # pyright: ignore
        )

        response = await self.stream.recv(channel=f"completion_request:{message.id}")
        completions: List[Completion] = response.data
        return [
            CompletionDropdownItem(
                content=completion["content"],
                position=completion["position"],
                main=(completion["display"] if completion["display"] is not None else completion["content"]),
            )
            for completion in completions
        ]

    # These 2 functions are very similar to their synchronous versions
    async def _async_input_cursor_position_changed(self, cursor_position: int) -> None:
        if (
            self.input_widget is not None  # pyright: ignore
            and not self.history_suggester.just_moved(self.input_widget.value)
        ):
            matches = await self._get_completions()
            self._mentat_sync_state(self.input_widget.value, cursor_position, matches)

    async def _async_input_value_changed(self, value: str) -> None:
        if (
            self.input_widget is not None  # pyright: ignore
            and not self.history_suggester.just_moved(value)
        ):
            matches = await self._get_completions()
            self._mentat_sync_state(
                value,
                self.input_widget.cursor_position,
                matches,  # pyright: ignore
            )

    # Since we do the autocomplete matching on the backend, we completely change this function
    # to not do any matching of its own
    def _mentat_sync_state(self, value: str, input_cursor_position: int, matches: List[DropdownItem]):
        self.child.matches = matches
        if matches:
            self.styles.width = max(len(match.main) for match in matches) + 2

        self.display = len(matches) > 0 and value != "" and self.input_widget.has_focus
        self.cursor_home()
        self.reposition(input_cursor_position)
        self.child.refresh()

    # By default the dropdown can only be below the input, but since our input is always at the bottom of the screen
    # we want the opposite, so we patch this function to drop up instead of down
    @override
    def reposition(
        self,
        input_cursor_position: int | None = None,
        scroll_target_adjust_y: int = 0,
    ) -> None:
        if self.input_widget is None:  # pyright: ignore
            return

        if input_cursor_position is None:
            input_cursor_position = self.input_widget.cursor_position  # pyright: ignore

        top, right, bottom, left = self.styles.margin  # pyright: ignore
        x, y, width, height = self.input_widget.content_region  # pyright: ignore
        # This is the line we change to fix the position
        line_below_cursor = (
            y
            + scroll_target_adjust_y
            - min(
                int(self.styles.max_height.value),  # pyright: ignore
                len(self.child.matches),
            )
        )

        cursor_screen_position = x + (  # pyright: ignore
            input_cursor_position - self.input_widget.view_position
        )
        self.styles.margin = (
            line_below_cursor,
            right,
            bottom,
            cursor_screen_position,
        )
