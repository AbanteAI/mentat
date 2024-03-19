from pathlib import Path

from mentat.errors import SampleError
from mentat.parsers.git_parser import GitParser
from mentat.python_client.client import PythonClient
from mentat.sampler.sample import Sample
from mentat.sampler.utils import setup_repo
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import convert_string_to_asynciter


async def generate_finetune(
    sample: Sample,
    cwd: Path | str | None = None,
    format: str = "gpt",
    include_system_prompt: bool = False,
):
    """Generate a fine-tuning example from the sample using the given format"""
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
    if include_system_prompt:
        system_prompt = ctx.config.parser.get_system_prompt()
        conversation.append({"role": "system", "content": system_prompt})
    if paths:
        code_message = await ctx.code_context.get_code_message(0)
        conversation.append({"role": "system", "content": code_message})
    for message in sample.message_history:
        if message["role"] == "user":
            conversation.append({"role": "user", "content": message["content"]})
        elif message["role"] == "assistant":
            generator = convert_string_to_asynciter(message["content"], 100)
            parsed_llm_response = await GitParser().stream_and_parse_llm_response(generator)
            formatted_content = ctx.config.parser.file_edits_to_llm_message(parsed_llm_response)
            conversation.append({"role": "assistant", "content": formatted_content})
    conversation.append({"role": "user", "content": sample.message_prompt})
    message_example = sample.message_edit or ""
    if sample.diff_edit:  # Convert any diff_edit to block format for answer
        parsed_llm_response = GitParser().parse_llm_response(sample.diff_edit)
        message_example += ctx.config.parser.file_edits_to_llm_message(parsed_llm_response)
    conversation.append({"role": "assistant", "content": message_example})

    await python_client.shutdown()

    if format == "gpt":
        return {"messages": conversation}  # per openai fine-tuning instx
    elif format == "llama":
        from litellm.llms.prompt_templates.factory import llama_2_chat_pt

        text = llama_2_chat_pt(conversation)
        return {"text": text}  # per togetherai fine-tuning instx
    elif format == "mistral":
        from litellm.llms.prompt_templates.factory import mistral_instruct_pt

        text = mistral_instruct_pt(conversation)
        return {"text": text}
    else:
        raise SampleError(f"Unrecognized finetune format: {format}")
