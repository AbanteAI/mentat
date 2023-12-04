from __future__ import annotations

import json

import attr
from openai.types.chat import ChatCompletionMessageParam

from mentat.code_feature import get_consolidated_feature_refs
from mentat.git_handler import get_diff_for_file, get_paths_with_git_diffs
from mentat.parsers.git_parser import GitParser
from mentat.session_context import SessionContext
from mentat.session_input import collect_user_input


def parse_message(message: ChatCompletionMessageParam) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    elif isinstance(content, list) and len(content) > 0:
        content = content[0]
        if "text" in content and isinstance(content.get("text"), str): # type: ignore
            return content.get("text") # type: ignore
        else:
            return ""
    else:
        return ""


@attr.define
class Sample:
    repo: str = attr.field(default="")
    merge_base: str = attr.field(default="")
    diff: str = attr.field(default="")
    args: list[str] = attr.field(default=[])  # type: ignore
    messages: list[dict[str, str]] = attr.field(default=[])  # type: ignore
    edits: list[dict] = attr.field(default=[])  # type: ignore

    @classmethod
    async def from_context(cls, session_context: SessionContext) -> Sample:
        # Check for repo and merge_base in config
        stream = session_context.stream
        code_context = session_context.code_context
        config = session_context.config
        code_file_manager = session_context.code_file_manager
        conversation = session_context.conversation

        if not config.sample_repo:
            stream.send("Input sample repo: (e.g. 'https://github.com/your/repo')")
            config.sample_repo = (await collect_user_input()).data.strip()
        if not config.sample_merge_base:
            stream.send("Input sample merge base: (e.g. 'main')")
            config.sample_merge_base = (await collect_user_input()).data.strip()

        args = list[str]()
        if code_context.include_files:
            args += get_consolidated_feature_refs(
                [f for fs in code_context.include_files.values() for f in fs]
            )

        messages = list[dict[str, str]]()
        for m in conversation.get_messages():
            parsed = parse_message(m)
            if parsed and m["role"] in {"user", "assistant"}:
                messages.append({"role": m["role"], "content": parsed})

        # Use "undo" to separate edits and pre-edit diff to merge_base
        errors = code_file_manager.history.undo()
        assert not errors, f"Errors while undoing: {errors}"
        file_edits = code_file_manager.history.undone_edits[-1].copy()
        edits = [edit.asdict() for edit in file_edits]

        # Diff of commit to pre-edited code
        changed_files = get_paths_with_git_diffs(config.sample_merge_base)
        diff_lines: list[str] = []
        for file in changed_files:
            git_diff = get_diff_for_file(config.sample_merge_base, file)
            if git_diff:
                diff_lines += git_diff.split("\n")
            else:
                # Generate diff-like output for new files
                diff_lines += [
                    f"diff --git a/{file} b/{file}",
                    "new file mode 100644",
                    "--- /dev/null",
                    f"+++ b/{file}",
                    "@@ -0,0 +1 @@",
                ] + [f"+{line}" for line in file.read_text().split("\n")]
        if diff_lines:
            parsed_llm_response = GitParser().parse_string("\n".join(diff_lines))
            diff = "\n".join(parsed_llm_response.full_response)
        else:
            diff = ""

        await code_file_manager.history.redo()

        return cls(
            repo=config.sample_repo,
            merge_base=config.sample_merge_base,
            diff=diff,
            args=args,
            messages=messages,
            edits=edits,
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
