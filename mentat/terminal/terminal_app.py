from __future__ import annotations

import os
from asyncio import Event
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from rich.console import RenderableType
from rich.markup import escape
from textual import on
from textual.app import App, ComposeResult
from textual.widgets import Input, ProgressBar, RichLog, Static, Tree
from textual.widgets._tree import TreeNode
from typing_extensions import override

from mentat.session_stream import SessionStream, StreamMessage
from mentat.terminal.history_suggester import HistorySuggester
from mentat.terminal.patched_autocomplete import PatchedAutoComplete, PatchedDropdown
from mentat.terminal.themes import themes
from mentat.utils import fetch_resource, mentat_dir_path

if TYPE_CHECKING:
    from mentat.terminal.client import TerminalClient

css_path = Path("textual/terminal_app.tcss")
history_file_location = mentat_dir_path / "prompt_history"

change_delimiter = "=" * 60


class ContentContainer(Static):
    BINDINGS = [
        ("up", "history_up", "Move up in history"),
        ("down", "history_down", "Move down in history"),
    ]

    def __init__(
        self,
        stream: SessionStream,
        theme: dict[str, str],
        renderable: RenderableType = "",
        **kwargs: Any,
    ):
        self.stream = stream
        self.theme = theme
        self.input_event = Event()
        self.last_user_input = ""
        self.suggester = HistorySuggester(history_file=history_file_location)
        self.loading_bar = None
        self.cur_line = ""

        super().__init__(renderable, **kwargs)

    @override
    def compose(self) -> ComposeResult:
        self.content = RichLog(wrap=True, markup=True, auto_scroll=True)
        yield self.content
        # RichLogs can't edit existing lines, only add new ones, so we have a 'buffer' widget until we reach a new line.
        self.last_content = Static(self.cur_line, classes="content-piece")
        yield self.last_content
        yield PatchedAutoComplete(
            Input(
                classes="user-input",
                disabled=True,
                suggester=self.suggester,
            ),
            PatchedDropdown(self.stream, self.suggester),
        )
        self.add_content("Type 'q' or use Ctrl-C to quit at any time.\n", color="cyan")
        self.add_content("What can I do for you?\n", color="blue")

    @on(Input.Submitted)
    def on_user_input(self, event: Input.Submitted):
        self.last_user_input = event.value
        self.suggester.append_to_history(event.value)
        self.input_event.set()

    async def collect_user_input(self, default_prompt: str) -> str:
        self.input_event.clear()

        user_input = self.query_one(Input)
        user_input.disabled = False
        user_input.value = default_prompt
        user_input.focus()
        await self.input_event.wait()
        user_input.value = ""
        user_input.disabled = True

        self.add_content(f">>> {self.last_user_input}\n", color=self.theme["prompt"])
        return self.last_user_input

    def action_history_up(self):
        history = self.suggester.move_up()
        if history is not None:
            user_input = self.query_one(Input)
            user_input.value = history
            user_input.cursor_position = len(history)

    def action_history_down(self):
        history = self.suggester.move_down()
        if history is not None:
            user_input = self.query_one(Input)
            user_input.value = history
            user_input.cursor_position = len(history)

    def start_loading(self):
        if not self.loading_bar:
            self.loading_bar = ProgressBar(id="loading-display", show_percentage=False, show_eta=False)
            self.mount(self.loading_bar)

    def end_loading(self):
        if self.loading_bar is not None:
            self.loading_bar.remove()
            self.loading_bar = None

    def add_content(self, new_content: str, color: str | None = None):
        new_content = escape(new_content)
        lines = [f"[{color}]{line}[/{color}]" if color else line for line in new_content.split("\n")]
        for line in lines[:-1]:
            line = self.cur_line + line
            self.cur_line = ""
            self.content.write(line)
        self.cur_line += lines[-1]
        self.last_content.update(self.cur_line)
        self.scroll_end(animate=False)


class ContextContainer(Static):
    def _build_path_tree(self, files: list[str], cwd: Path):
        """Builds a tree of paths from a list of CodeFiles."""
        tree = dict[str, Any]()
        for file in files:
            path = os.path.relpath(file, cwd)
            parts = Path(path).parts
            current_level = tree
            for part in parts:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
        return tree

    def _build_sub_tree(
        self,
        cur_path: Path,
        root: TreeNode[Any],
        children: Dict[str, Any],
        git_diff_paths: Set[Path],
        untracked_paths: Set[Path],
        untracked: bool = False,
    ):
        for child, grandchildren in children.items():
            new_path = cur_path / child
            path_untracked = new_path in untracked_paths or untracked
            if path_untracked:
                label = f"[red]! {child}[/red]"
            else:
                label = child
            if not grandchildren:
                if new_path in git_diff_paths:
                    label = f"[green]* {child}[/green]"
                root.add_leaf(label)
            else:
                child_node = root.add(label, expand=True)
                self._build_sub_tree(
                    new_path,
                    child_node,
                    grandchildren,
                    git_diff_paths,
                    untracked_paths,
                    path_untracked,
                )

    def _build_tree_widget(
        self,
        files: list[str],
        cwd: Path,
        git_diff_paths: Set[Path],
        untracked_paths: Set[Path],
    ) -> Tree[Any]:
        path_tree = self._build_path_tree(files, cwd)
        tree: Tree[Any] = Tree(f"[blue]{cwd.name}[/blue]")
        tree.root.expand()
        self._build_sub_tree(cwd, tree.root, path_tree, git_diff_paths, untracked_paths)
        return tree

    def update_context(
        self,
        cwd: Path,
        diff_context_display: Optional[str],
        auto_context_tokens: int,
        features: List[str],
        git_diff_paths: Set[Path],
        git_untracked_paths: Set[Path],
        total_tokens: int,
        total_cost: float,
    ):
        feature_tree = self._build_tree_widget(features, cwd, git_diff_paths, git_untracked_paths)

        context_header = ""
        context_header += "[blue bold]Code Context:[/blue bold]"
        context_header += f"\nTokens: [yellow]{total_tokens}[/yellow]"
        context_header += f"\nTotal Session Cost: [yellow]${total_cost:.2f}[/yellow]"
        context_header += f"\nDirectory: {cwd}"
        if diff_context_display:
            context_header += f"\nDiff:[green]{diff_context_display}[/green]"
        if auto_context_tokens > 0:
            context_header += f"\nAuto-Context: Enabled\nAuto-Context Tokens: {auto_context_tokens}"
        else:
            context_header += "\nAuto-Context: [yellow]Disabled[/yellow]"

        context_header += "\nIncluded Files:"
        if not features:
            context_header += " [yellow]None[/yellow]"

        self.remove_children()
        self.mount(Static(context_header))
        if features:
            self.mount(feature_tree)


css_resource = fetch_resource(css_path)
with css_resource.open("r") as css_file:
    css = css_file.read()


class TerminalApp(App[None]):
    BINDINGS = [("ctrl+c", "on_interrupt", "Send interrupt")]
    CSS = css
    TITLE = "Mentat"

    def __init__(self, client: TerminalClient, **kwargs: Any):
        self.client = client
        self.command_autocomplete = False
        self.last_filepath = None
        super().__init__(**kwargs)

    @override
    def compose(self) -> ComposeResult:
        self.dark = self.client.config.theme == "dark"
        self.theme = themes[self.client.config.theme]
        self.content_container = ContentContainer(self.client.session.stream, self.theme)
        yield self.content_container
        yield ContextContainer()

    def display_stream_message(self, message: StreamMessage):
        end = "\n"
        color = None
        content_container = self.query_one(ContentContainer)

        if isinstance(message.extra.get("end"), str):
            end = message.extra["end"]
        if isinstance(message.extra.get("color"), str):
            color = message.extra["color"]
        if isinstance(message.extra.get("style"), str):
            style = message.extra["style"]
            color = self.theme[style]
        if message.extra.get("delimiter", False):
            content_container.add_content(f"{change_delimiter}\n")
        filepath = message.extra.get("filepath")
        if filepath != self.last_filepath:
            if self.last_filepath:
                content_container.add_content(f"{change_delimiter}\n\n")
            if filepath:
                filepath_display, filepath_display_type = message.extra.get("filepath_display", filepath)
                content_container.add_content(
                    f"{filepath_display}\n",
                    color=(
                        "bright_green"
                        if filepath_display_type == "creation"
                        else (
                            "bright_red"
                            if filepath_display_type == "deletion"
                            else ("yellow" if filepath_display_type == "rename" else "bright_blue")
                        )
                    ),
                )
                content_container.add_content(f"{change_delimiter}\n")
            self.last_filepath = filepath

        content = str(message.data) + end
        content_container.add_content(content, color)

    async def get_user_input(self, default_prompt: str, command_autocomplete: bool) -> str:
        # This is a really janky way to pass command_autocomplete to Dropdown._get_completions(),
        # but I couldn't think of anything better
        self.command_autocomplete = command_autocomplete
        content_container = self.query_one(ContentContainer)
        return await content_container.collect_user_input(default_prompt)

    def update_context(
        self,
        cwd: Path,
        diff_context_display: Optional[str],
        auto_context_tokens: int,
        features: List[str],
        git_diff_paths: Set[Path],
        git_untracked_paths: Set[Path],
        total_tokens: int,
        total_cost: float,
    ):
        context_container = self.query_one(ContextContainer)
        context_container.update_context(
            cwd,
            diff_context_display,
            auto_context_tokens,
            features,
            git_diff_paths,
            git_untracked_paths,
            total_tokens,
            total_cost,
        )

    def action_on_interrupt(self):
        self.client.send_interrupt()

    def disable_app(self):
        self.query_one(Input).disabled = True
        self.end_loading()

    def start_loading(self):
        self.query_one(ContentContainer).start_loading()

    def end_loading(self):
        self.query_one(ContentContainer).end_loading()
