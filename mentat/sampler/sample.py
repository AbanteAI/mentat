from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import attr
from git import Repo  # type: ignore
from git.exc import GitCommandError
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.code_feature import get_consolidated_feature_refs
from mentat.errors import HistoryError, SampleError
from mentat.git_handler import get_diff_active, get_hexsha_active
from mentat.python_client.client import PythonClient
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import collect_user_input
from mentat.utils import clone_repo, get_relative_path


def warn(msg: Any):
    print(f"\033[93m[WARNING] {msg}\033[0m")


def parse_message(message: ChatCompletionMessageParam) -> str:
    content = message.get("content")
    if isinstance(content, str):
        if message.get("role") == "assistant" and "\n@@start\n" in content:
            return content.split("@@start\n")[0]  # TODO: split properly
        return content
    elif isinstance(content, list) and len(content) > 0:
        content = content[0]
        if "text" in content and isinstance(content.get("text"), str):  # type: ignore
            return content.get("text")  # type: ignore
        else:
            return ""
    else:
        return ""


def apply_diff_to_repo(diff: str, repo: Repo) -> str | None:
    try:
        # Save self.diff_merge_base to a temporary .diff file
        with open(".mentat_diff_merge_base.diff", "w") as f:
            f.write(diff)
        repo.git.execute(["git", "apply", ".mentat_diff_merge_base.diff"])
        repo.git.add(".")
        repo.git.commit("-m", "mentat_eval_temp")
    except GitCommandError as e:
        return str(e)
    finally:
        os.remove(".mentat_diff_merge_base.diff")


def setup_repo(sample: Sample, path_to_repo: Path | str | None) -> Path:
    if path_to_repo is None:
        cwd = clone_repo(
            url=sample.repo,
            local_dir_name=sample.repo.split("/")[-1],
            refresh=False,
        )
        if cwd is None:
            raise SampleError(f"Error cloning {sample.repo}")
    else:
        cwd = Path(path_to_repo)
    os.chdir(cwd)
    repo = Repo(".")
    repo.git.checkout(sample.merge_base)
    repo.head.reset(index=True, working_tree=True)  # git reset --hard
    if sample.diff_merge_base:
        try:
            repo.git.branch("-D", "mentat_eval_temp")
        except GitCommandError:
            pass
        repo.git.checkout("-b", "mentat_eval_temp")
        errors = apply_diff_to_repo(sample.diff_merge_base, repo)
        if errors:
            raise SampleError(f"Error applying diff_merge_base: {errors}")
    if sample.diff_active:
        errors = apply_diff_to_repo(sample.diff_active, repo)
        if errors:
            raise SampleError(f"Error applying diff_active: {errors}")
    hexsha_active = get_hexsha_active()
    if hexsha_active != sample.hexsha_active:
        warn("hexsha_active does not match sample. Continuing anyway.")
    return cwd


async def run_mentat_on_sample(sample: Sample, cwd: Path):
    # Initialize Mentat PythonClient with args and messages
    paths = list[Path]()
    for a in sample.args:
        if a.startswith("--"):
            break  # TODO: Handle other mentat args?
        paths.append(Path(a))
    python_client = PythonClient(cwd=cwd, paths=paths)
    await python_client.startup()
    session_context = SESSION_CONTEXT.get()
    conversation = session_context.conversation
    conversation_history = list[ChatCompletionMessageParam]()
    sample_prompt: str | None = None
    for m in sample.messages[::-1]:
        role, content = m.get("role"), m.get("content", "")
        if role == "user":
            if sample_prompt is None:
                sample_prompt = content
            else:
                msg = ChatCompletionUserMessageParam(role="user", content=content)
                conversation_history.insert(0, msg)
        elif role == "assistant":
            if sample_prompt is None:
                warn(
                    "Ignoring assistant message after last user"
                    f" prompt,'{content[:15]}'..."
                )
            else:
                msg = ChatCompletionAssistantMessageParam(
                    role="assistant", content=content
                )
                conversation_history.insert(0, msg)
        else:
            warn(
                f"Only user and assistant messages are supported. Got {m['role']}."
                " Skipping"
            )
            continue
    if sample_prompt is None:
        raise SampleError("Sample prompt not found in messages.")
    for msg in conversation_history:
        conversation.add_message(msg)

    await python_client.call_mentat_auto_accept(sample_prompt)
    await python_client.wait_for_edit_completion()
    await python_client.shutdown()


@attr.define
class Sample:
    # TODO: enforce required fields
    title: str = attr.field(default="")
    description: str = attr.field(default="")
    repo: str = attr.field(default="")
    merge_base: str | None = attr.field(default=None)
    diff_merge_base: str = attr.field(default="")
    diff_active: str = attr.field(default="")
    hexsha_active: str = attr.field(default="")
    messages: list[dict[str, str]] = attr.field(default=[])  # type: ignore
    args: list[str] = attr.field(default=[])  # type: ignore
    diff_edit: str = attr.field(default="")
    hexsha_edit: str = attr.field(default="")
    test_command: str = attr.field(default="")
    version: str = attr.field(default="0.1.0")

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

        stream.send("Input sample data", color="light_blue")
        repo = config.sample_repo
        if not repo:
            stream.send("Repo URL: (e.g. 'https://github.com/your/repo')")
            config.sample_repo = (await collect_user_input()).data.strip()
            repo = config.sample_repo  # TODO: Save to .mentat_config.json
        stream.send("Sample Title:")
        title = (await collect_user_input()).data.strip() or ""
        stream.send("Description: (optional)")
        description = (await collect_user_input()).data.strip() or ""
        stream.send("Test Command: (optional, e.g. 'pytest -k foo')")
        test_command = (await collect_user_input()).data.strip() or ""

        messages = list[dict[str, str]]()
        for m in conversation.get_messages():
            parsed = parse_message(m)
            if parsed and m["role"] in {"user", "assistant"}:
                # TODO Replace mentat-formatted edits with git diffs
                messages.append({"role": m["role"], "content": parsed})
                # TODO Remove edits altogether from last assistant message

        args = list[str]()
        if code_context.include_files:
            feature_refs = get_consolidated_feature_refs(
                [f for fs in code_context.include_files.values() for f in fs]
            )
            args += [get_relative_path(Path(f), cwd).as_posix() for f in feature_refs]

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

    def save(self, fname: str) -> None:
        with open(fname, "w") as f:
            json.dump(attr.asdict(self), f, indent=4)

    @classmethod
    def load(cls, fname: str) -> Sample:
        with open(fname, "r") as f:
            return cls(**json.loads(f.read()))

    async def eval(self, path_to_repo: Path | str | None = None) -> dict[str, str]:
        cwd = setup_repo(self, path_to_repo)
        await run_mentat_on_sample(self, cwd)

        # EVALUATE
        diff_eval = get_diff_active() or ""  # TODO: subtract diff_active
        hexsha_eval = get_hexsha_active()

        # Run the test command
        test_result: str = ""
        if self.test_command:
            test_result = subprocess.check_output(
                self.test_command,
                text=True,
            )
        # TODO: Run the LLM evaluations from benchmark
        # TODO: Save the results

        return {
            "diff_eval": diff_eval,
            "hexsha_eval": hexsha_eval,
            "test_result": test_result,
        }
