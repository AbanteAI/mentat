import os
from asyncio import Event
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from rich.console import RenderableType
from rich.markup import escape
from textual import on
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import Header, Input, Static, Tree
from textual.widgets._tree import TreeNode
from typing_extensions import override

from mentat.session_stream import StreamMessage
from mentat.utils import fetch_resource

css_path = Path("textual/terminal_app.tcss")


class ContentDisplay(Static):
    content = reactive("")

    def add_content(self, new_content: str, color: Optional[str] = None):
        new_content = escape(new_content)
        if color is not None:
            new_content = f"[{color}]{new_content}[/{color}]"
        self.content += new_content

    def watch_content(self, content: str):
        self.update(content)


class ContentContainer(Static):
    def __init__(self, renderable: RenderableType = "", **kwargs: Any):
        self.input_event = Event()
        self.last_user_input = ""

        super().__init__(renderable, **kwargs)

    @override
    def compose(self) -> ComposeResult:
        yield ContentDisplay()
        # TODO: Add suggester (equivalent to current history completion), add auto complete
        yield Input(classes="user-input", disabled=True)

    @on(Input.Submitted)
    def on_user_input(self, event: Input.Submitted):
        self.last_user_input = event.value
        self.input_event.set()

    async def collect_user_input(
        self, default_prompt: str, plain: bool, command_autocomplete: bool
    ) -> str:
        self.input_event.clear()

        user_input = self.query_one(Input)
        user_input.disabled = False
        user_input.focus()
        await self.input_event.wait()
        user_input.value = ""
        user_input.disabled = True

        content_display = self.query_one(ContentDisplay)
        # TODO: This color shouldn't be hardcoded in (even though it previously was)
        content_display.add_content(f">>> {self.last_user_input}\n", color="white")
        return self.last_user_input


class ContextContainer(Static):
    # TODO: Remove all hardcoded colors
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
    ):
        for child, grandchildren in children.items():
            new_path = cur_path / child
            if not grandchildren:
                if new_path in git_diff_paths:
                    label = f"[green]* {child}[/green]"
                else:
                    label = child
                root.add_leaf(label)
            else:
                child_node = root.add(child, expand=True)
                self._build_sub_tree(
                    new_path, child_node, grandchildren, git_diff_paths
                )

    def _build_tree_widget(
        self, files: list[str], cwd: Path, git_diff_paths: Set[Path]
    ) -> Tree[Any]:
        path_tree = self._build_path_tree(files, cwd)
        tree: Tree[Any] = Tree(f"[blue]{cwd.name}[/blue]")
        tree.root.expand()
        self._build_sub_tree(cwd, tree.root, path_tree, git_diff_paths)
        return tree

    def update_context(
        self,
        cwd: Path,
        diff_context_display: str,
        auto_context_tokens: int,
        features: List[str],
        auto_features: List[str],
        git_diff_paths: Set[Path],
    ):
        self.remove_children()

        feature_tree = self._build_tree_widget(features, cwd, git_diff_paths)
        auto_feature_tree = self._build_tree_widget(auto_features, cwd, git_diff_paths)

        context_header = ""
        context_header += "[blue]Code Context:[/blue]"
        context_header += f"\nDirectory: {cwd}"
        context_header += f"\nDiff:[green]{diff_context_display}[/green]"
        if auto_context_tokens > 0:
            context_header += (
                f"\nAuto-Context: Enabled\nAuto-Context Tokens: {auto_context_tokens}"
            )
        else:
            context_header += "\nAuto-Context: [yellow]Disabled[/yellow]"

        context_header += "\nIncluded Files:"
        if not features:
            context_header += " [yellow]None[/yellow]"
        self.mount(Static(context_header))

        if features:
            self.mount(feature_tree)

        if auto_features:
            self.mount(Static("Auto-Included Features:"))
            self.mount(auto_feature_tree)


css_resource = fetch_resource(css_path)
with css_resource.open("r") as css_file:
    css = css_file.read()


# TODO: Should be light mode if terminal is light mode
class TerminalApp(App[None]):
    # TODO: Call _handle_sig_int on ctrl-c
    BINDINGS = []  # [("ctrl+c", "", "")]
    CSS = css
    TITLE = "Mentat"

    @override
    def compose(self) -> ComposeResult:
        yield Header()
        yield ContentContainer()
        yield ContextContainer()

    def display_stream_message(
        self, message: StreamMessage, theme: dict[str, str] | None
    ):
        end = "\n"
        color = None
        if message.extra:
            if isinstance(message.extra.get("end"), str):
                end = message.extra["end"]
            if isinstance(message.extra.get("color"), str):
                color = message.extra["color"]
            if isinstance(message.extra.get("style"), str):
                style = message.extra["style"]
                if theme is not None:
                    color = theme[style]

        content_display = self.query_one(ContentDisplay)
        content = message.data + end
        content_display.add_content(content, color)

    async def get_user_input(
        self, default_prompt: str, plain: bool, command_autocomplete: bool
    ) -> str:
        content_container = self.query_one(ContentContainer)
        return await content_container.collect_user_input(
            default_prompt, plain, command_autocomplete
        )

    def update_context(
        self,
        cwd: Path,
        diff_context_display: str,
        auto_context_tokens: int,
        features: List[str],
        auto_features: List[str],
        git_diff_paths: Set[Path],
    ):
        context_container = self.query_one(ContextContainer)
        context_container.update_context(
            cwd,
            diff_context_display,
            auto_context_tokens,
            features,
            auto_features,
            git_diff_paths,
        )
