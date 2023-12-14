from __future__ import annotations

import json

import attr


@attr.define
class Sample:
    # TODO: enforce required fields
    title: str = attr.field(default="")
    description: str = attr.field(default="")
    id: str = attr.field(default="")
    parent_id: str = attr.field(default="")
    repo: str = attr.field(default="")
    merge_base: str | None = attr.field(default=None)
    diff_merge_base: str = attr.field(default="")
    diff_active: str = attr.field(default="")
    messages: list[dict[str, str]] = attr.field(default=[])  # type: ignore
    args: list[str] = attr.field(default=[])  # type: ignore
    diff_edit: str = attr.field(default="")
    test_command: str = attr.field(default="")
    version: str = attr.field(default="0.1.0")

    def save(self, fname: str) -> None:
        with open(fname, "w") as f:
            json.dump(attr.asdict(self), f, indent=4)

    @classmethod
    def load(cls, fname: str) -> Sample:
        with open(fname, "r") as f:
            return cls(**json.loads(f.read()))
