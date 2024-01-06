from pathlib import Path

from mentat.parsers.git_parser import GitParser
from mentat.python_client.client import PythonClient
from mentat.sampler.utils import setup_repo
from mentat.session_context import SESSION_CONTEXT


async def generate_finetune_gpt(sample, cwd: Path | str | None = None):
    """Generate a fine-tuning example from the sample for GPT-3.5

    {"messages": [{"role": "user", "content": "Hello, world!"}, ...]}
    """
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
    ctx = SESSION_CONTEXT.get()

    # Build the conversation
    conversation = list[dict[str, str]]()
    if paths:
        code_message = await ctx.code_context.get_code_message(0)
        conversation.append({"role": "system", "content": code_message})
    # TODO: Ignore conversation_history for now because file_edits are not yet included
    # conversation += sample.message_history[::-1]
    conversation.append({"role": "user", "content": sample.message_prompt})
    message_example = sample.message_edit or ""
    if sample.diff_edit:  # Convert any diff_edit to block format for answer
        parsed_llm_response = GitParser().parse_string(sample.diff_edit)
        message_example += ctx.config.parser.file_edits_to_llm_message(
            parsed_llm_response
        )
    conversation.append({"role": "assistant", "content": message_example})

    await python_client.shutdown()
    return {"messages": conversation}
