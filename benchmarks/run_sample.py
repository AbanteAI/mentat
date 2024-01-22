from pathlib import Path
from typing import Any

from git import Repo

from mentat.errors import SampleError
from mentat.git_handler import get_git_diff
from mentat.parsers.git_parser import GitParser
from mentat.python_client.client import PythonClient
from mentat.sampler.sample import Sample
from mentat.sampler.utils import get_active_snapshot_commit, setup_repo
from mentat.session_context import SESSION_CONTEXT


async def setup_python_client(
    sample: Sample, cwd: Path | str | None = None
) -> PythonClient:
    repo = setup_repo(
        url=sample.repo,
        cwd=cwd,
        commit=sample.merge_base,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)

    # Run sample in PythonClient
    paths = list[Path]()
    for a in sample.context:
        paths.append(Path(a))
    python_client = PythonClient(cwd=cwd, paths=paths)
    await python_client.startup()
    session_context = SESSION_CONTEXT.get()
    conversation = session_context.conversation
    for msg in sample.message_history:
        if msg["role"] == "user":
            conversation.add_user_message(msg["content"])
        elif msg["role"] == "assistant":
            parsed_llm_response = GitParser().parse_llm_response(msg["content"])
            content = session_context.config.parser.file_edits_to_llm_message(
                parsed_llm_response
            )
            conversation.add_model_message(content, [], parsed_llm_response)
        else:
            raise SampleError(f"Invalid role found in message_history: {msg['role']}")
    return python_client


async def run_sample(sample: Sample, cwd: Path | str | None = None) -> dict[str, Any]:
    """Run a sample using Mentat and return the resulting diff"""
    python_client = await setup_python_client(sample, cwd)

    session_context = SESSION_CONTEXT.get()
    conversation = session_context.conversation
    cwd = session_context.cwd
    cost_tracker = session_context.cost_tracker

    repo = Repo(cwd)
    commit_active = get_active_snapshot_commit(repo)

    await python_client.call_mentat_auto_accept(sample.message_prompt)
    await python_client.shutdown()

    # Get the diff between pre- and post-edit
    transcript_messages = conversation.literal_messages.copy()

    message_eval = str(transcript_messages[-1].get("message", ""))
    diff_eval = get_git_diff(commit_active or "HEAD", cwd=cwd)

    return {
        "id": sample.id,
        "message_eval": message_eval,
        "diff_eval": diff_eval,
        "cost": cost_tracker.total_cost,
        "tokens": cost_tracker.total_tokens,
        "transcript": {
            "id": sample.id,
            "messages": transcript_messages,
        },
    }
