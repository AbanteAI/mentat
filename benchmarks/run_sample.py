from pathlib import Path
from typing import Any

from mentat.errors import SampleError
from mentat.git_handler import get_git_diff
from mentat.parsers.git_parser import GitParser
from mentat.python_client.client import PythonClient
from mentat.sampler.sample import Sample
from mentat.sampler.utils import get_active_snapshot_commit, setup_repo
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import convert_string_to_asynciter


async def run_sample(sample: Sample, cwd: Path | str | None = None) -> dict[str, Any]:
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
    cost_tracker = session_context.cost_tracker
    for msg in sample.message_history:
        if msg["role"] == "user":
            conversation.add_user_message(msg["content"])
        elif msg["role"] == "assistant":
            generator = convert_string_to_asynciter(msg["content"], 100)
            parsed_llm_response = await GitParser().stream_and_parse_llm_response(
                generator
            )
            content = session_context.config.parser.file_edits_to_llm_message(
                parsed_llm_response
            )
            conversation.add_model_message(content, [], parsed_llm_response)
        else:
            raise SampleError(f"Invalid role found in message_history: {msg['role']}")
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
