from pathlib import Path

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.errors import SampleError
from mentat.git_handler import get_git_diff
from mentat.python_client.client import PythonClient
from mentat.sampler.utils import get_active_snapshot_commit, setup_repo
from mentat.session_context import SESSION_CONTEXT


async def run_sample(sample, cwd: Path | str | None = None) -> tuple[str, str]:
    """Run a sample using Mentat and return the resulting diff"""

    repo = setup_repo(
        url=sample.repo,
        cwd=cwd,
        commit=sample.merge_base,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)

    # Make a commit from the pre-edited state (should match diff_active)
    commit_active = get_active_snapshot_commit(repo)

    # Run sample in PythonClient
    paths = list[Path]()
    for a in sample.context:
        paths.append(Path(a))
    python_client = PythonClient(cwd=cwd, paths=paths)
    await python_client.startup()
    session_context = SESSION_CONTEXT.get()
    conversation = session_context.conversation
    for msg in sample.message_history:
        msg_cls = {
            "user": ChatCompletionUserMessageParam,
            "assistant": ChatCompletionAssistantMessageParam,
        }.get(msg["role"])
        if msg_cls is None:
            raise SampleError(f"Invalid role found in message_history: {msg['role']}")
        conversation.add_message(msg_cls(role=msg["role"], content=msg["content"]))
    await python_client.call_mentat_auto_accept(sample.message_prompt)
    await python_client.shutdown()

    # Get the diff between pre- and post-edit
    transcript_message = conversation.literal_messages[-1]
    message_eval = transcript_message["message"]
    diff_eval = get_git_diff(commit_active or "HEAD", cwd=cwd)

    return message_eval, diff_eval
