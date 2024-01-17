from __future__ import annotations

import json
from pathlib import Path

import attr

from mentat.errors import SampleError
from mentat.sampler import __version__


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
    message_history: list[dict[str, str]] = attr.field(default=[])  # type: ignore
    message_prompt: str = attr.field(default="")
    message_edit: str = attr.field(default="")
    context: list[str] = attr.field(default=[])  # type: ignore
    diff_edit: str = attr.field(default="")
    test_command: str = attr.field(default="")
    version: str = attr.field(default=__version__)

    def save(self, fname: str | Path) -> None:
        with open(Path(fname), "w") as f:
            json.dump(attr.asdict(self), f, indent=4)

    @classmethod
    def load(cls, fname: str | Path) -> Sample:
        with open(fname, "r") as f:
            kwargs = json.load(f)
            _version = kwargs.get("version")
            if _version and _version < "0.2.0":
                kwargs["message_history"] = kwargs.get("message_history", [])[::-1]
                kwargs["version"] = "0.2.0"
                _version = kwargs["version"]
            if _version != __version__:
                raise SampleError(
                    f"Warning: sample version ({_version}) does not match current"
                    f" version ({__version__})."
                )
            return cls(**kwargs)
