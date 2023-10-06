from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Generator

from mentat.errors import MentatError
from mentat.git_handler import get_non_gitignored_files
from mentat.utils import sha256


class Node:
    def __init__(self, path: Path, parent: Node | None = None):
        self.path = path.resolve()
        self.parent = parent
        self.children = dict[str, Node]()
        self.lock = asyncio.Lock()
        self.refresh()

    def __getitem__(self, path: Path | str) -> "Node":
        if isinstance(path, str):
            path = Path(path)
        if path.is_absolute():
            path = path.relative_to(self.root().path)
        if path == Path("."):
            return self

        stem = path.parts[0]
        if stem not in self.children:
            raise KeyError(f"Node {self.path} has no child {stem}")
        elif len(path.parts) == 1:
            return self.children[stem]
        else:
            return self.children[stem][Path(*path.parts[1:])]

    def iter_nodes(
        self, include_dirs: bool = True, include_files: bool = True
    ) -> Generator[Node, None, None]:
        if self.path.is_dir():
            if include_dirs:
                yield self
            for child in self.children.values():
                yield from child.iter_nodes(include_dirs, include_files)
        elif include_files:
            yield self

    def refresh(self):
        if self.path.is_dir():
            tracked_children = {p.parts[0] for p in get_non_gitignored_files(self.path)}
            untracked_children = (
                set(self.children.keys()) - tracked_children
            )  # Added manually
            all_children = tracked_children.union(untracked_children)
            for child in sorted(all_children):
                if child in self.children:
                    self.children[child].refresh()
                else:
                    self.children[child] = Node(Path(self.path / child), self)

    def root(self) -> "Node":
        return self if self.parent is None else self.parent.root()

    def relative_path(self) -> Path:
        return self.path.relative_to(self.root().path)

    def display(self, prefix: str = ""):
        print(prefix + self.path.name)
        for child in self.children.values():
            child.display(prefix + "  ")

    async def read_text(self) -> str:
        if self.path.is_dir():
            raise MentatError(f"Cannot read text from directory {self.path}")
        async with self.lock:
            return self.path.read_text()

    async def write_text(self, text: str):
        if self.path.is_dir():
            raise MentatError(f"Cannot write text to directory {self.path}")
        async with self.lock:
            self.path.write_text(text)

    async def get_checksum(self) -> str:
        if self.path.is_dir():
            _checksums = dict[str, str]()
            for name in sorted(self.children.keys()):
                _c = await self.children[name].get_checksum()
                _checksums[name] = _c
            return sha256(str(_checksums))
        else:
            text = await self.read_text()
            return sha256(text)
