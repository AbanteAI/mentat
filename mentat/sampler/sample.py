from __future__ import annotations

import json
from pathlib import Path

import attr
from openai.types.chat import ChatCompletionMessageParam

from mentat.code_feature import get_consolidated_feature_refs
from mentat.errors import HistoryError
from mentat.git_handler import get_diff_active, get_hexsha_active
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import collect_user_input
from mentat.utils import get_relative_path


def parse_message(message: ChatCompletionMessageParam) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    elif isinstance(content, list) and len(content) > 0:
        content = content[0]
        if "text" in content and isinstance(content.get("text"), str):  # type: ignore
            return content.get("text")  # type: ignore
        else:
            return ""
    else:
        return ""


@attr.define
class Sample:
    # TODO: enforce required fields
    title: str = attr.field(default="")
    description: str = attr.field(default="")
    repo: str | None = attr.field(default=None)
    merge_base: str | None = attr.field(default=None)
    diff_merge_base: str = attr.field(default="")
    diff_active: str = attr.field(default="")
    hexsha_active: str = attr.field(default="")
    messages: list[dict[str, str]] = attr.field(default=[])  # type: ignore
    args: list[str] = attr.field(default=[])  # type: ignore
    diff_edit: str = attr.field(default="")
    hexsha_edit: str = attr.field(default="")
    test_command: str = attr.field(default="")
    version: str = attr.field(default="0.1.0", init=False)

    @classmethod
    async def from_context(cls) -> Sample:
        # Check for repo and merge_base in config
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        config = session_context.config
        code_file_manager = session_context.code_file_manager
        conversation = session_context.conversation
        cwd = session_context.cwd

        if not config.sample_merge_base_target:
            merge_base = code_file_manager.history.merge_base
            if merge_base is None:
                raise HistoryError("EditHistory.merge_base was not set.")
            stream.send(
                "No sample_merge_base_target specified in config; using HEAD"
                f" ({merge_base}) as merge base."
            )

        stream.send("Input sample data:")
        repo = config.sample_repo
        if not repo:
            stream.send("  Repo URL: (e.g. 'https://github.com/your/repo')")
            config.sample_repo = (await collect_user_input()).data.strip()
            repo = config.sample_repo
        stream.send("  Sample Title:")
        title = (await collect_user_input()).data.strip() or ""
        stream.send("  Description: (optional)")
        description = (await collect_user_input()).data.strip() or ""
        stream.send("  Test Command: (optional, e.g. 'pytest -k foo')")
        test_command = (await collect_user_input()).data.strip() or ""

        messages = list[dict[str, str]]()
        for m in conversation.get_messages():
            parsed = parse_message(m)
            if parsed and m["role"] in {"user", "assistant"}:
                # TODO Remove mentat-formatted edits
                messages.append({"role": m["role"], "content": parsed})

        args = list[str]()
        if code_context.include_files:
            feature_refs = get_consolidated_feature_refs(
                [f for fs in code_context.include_files.values() for f in fs]
            )
            args += [str(get_relative_path(Path(f), cwd)) for f in feature_refs]

        return cls(
            title=title,
            description=description,
            repo=repo,
            merge_base=code_file_manager.history.merge_base,
            diff_merge_base=code_file_manager.history.diff_merge_base or "",
            diff_active=code_file_manager.history.diff_active or "",
            hexsha_active=code_file_manager.history.hexsha_active or "",
            messages=messages,
            args=args,
            diff_edit=get_diff_active() or "",  # TODO: subtract diff_active
            hexsha_edit=get_hexsha_active(),
            test_command=test_command,
        )

    def to_json(self) -> str:
        return json.dumps(attr.asdict(self), indent=4)

    def save(self, fname: str) -> None:
        with open(fname, "w") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, fname: str) -> Sample:
        with open(fname, "r") as f:
            return cls(**json.loads(f.read()))

    # def evaluate edits # with LLM # PROMPTS LOCATION

    # def evaluate auto-context:
    # Run, replace args with "-a"
    # precision/recall

    # def generate_finetune_sample
