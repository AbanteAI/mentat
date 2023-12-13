from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

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
from mentat.git_handler import get_diff_active
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


def apply_diff_to_repo(diff: str, repo: Repo, commit: bool = False) -> str | None:
    temp_id = uuid4().hex
    try:
        # Save self.diff_merge_base to a temporary .diff file
        with open(f".sample_{temp_id}.diff", "w") as f:
            f.write(diff)
        repo.git.execute(["git", "apply", f".sample_{temp_id}.diff"])
        if commit:
            repo.git.add(".")
            repo.git.commit("-m", f"sample_{temp_id}")
    except GitCommandError as e:
        return str(e)
    finally:
        os.remove(f".sample_{temp_id}.diff")


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
    repo.head.reset(index=True, working_tree=True)  # reset tracked files
    repo.git.execute(["git", "clean", "-fd"])  # remove untracked files/directories
    repo.git.fetch("--all")
    repo.git.checkout(sample.merge_base)
    if sample.diff_merge_base:
        errors = apply_diff_to_repo(sample.diff_merge_base, repo, commit=True)
        if errors:
            raise SampleError(f"Error applying diff_merge_base: {errors}")
    if sample.diff_active:
        errors = apply_diff_to_repo(sample.diff_active, repo)
        if errors:
            raise SampleError(f"Error applying diff_active: {errors}")
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

        merge_base = code_file_manager.history.merge_base
        if not merge_base:
            raise HistoryError(
                "EditHistory.merge_base was not set. You must interact with Mentat"
                " before generating a sample"
            )
        stream.send("Input sample data", color="light_blue")
        stream.send(
            f"Merge Base: {merge_base}. Press 'ENTER' to accept, or enter a new merge"
            " base commit."
        )
        merge_base = (await collect_user_input()).data.strip() or merge_base
        # TODO: set diff_merge_base here
        repo = config.sample_repo
        if not repo:
            remote_url = ""
            try:
                remote_url = subprocess.check_output(
                    ["git", "config", "--get", "remote.origin.url"],
                    text=True,
                ).strip()
            except subprocess.CalledProcessError:
                pass
            stream.send(
                f"Found repo URL: {remote_url}. Press 'ENTER' to accept, or enter a new"
                " URL."
            )
            response = (await collect_user_input()).data.strip()
            if response == "y":
                repo = remote_url
            else:
                repo = response
            config.sample_repo = repo

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
            id=uuid4().hex,
            parent_id=code_file_manager.history.last_sample_id or "",
            repo=repo,
            merge_base=code_file_manager.history.merge_base,
            diff_merge_base=code_file_manager.history.diff_merge_base or "",
            diff_active=code_file_manager.history.diff_active or "",
            messages=messages,
            args=args,
            diff_edit=get_diff_active() or "",  # TODO: subtract diff_active
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
            "test_result": test_result,
        }
