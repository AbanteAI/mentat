import random
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

import attr
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.code_feature import CodeFeature, get_code_message_from_features
from mentat.errors import SampleError
from mentat.python_client.client import PythonClient
from mentat.sampler.sample import Sample
from mentat.sampler.utils import setup_repo


async def remove_context(sample) -> Sample:
    """Return a duplicate sample with one context item removed and a warning message"""

    # Setup the repo and load context files
    repo = setup_repo(
        url=sample.repo,
        commit=sample.merge_base,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)
    python_client = PythonClient(cwd=Path("."), paths=[])
    await python_client.startup()

    context = [CodeFeature(cwd / p) for p in sample.context]
    i_target = random.randint(0, len(context) - 1)
    target = context[i_target]
    target_context = target.get_code_message(standalone=False)
    background_features = context[:i_target] + context[i_target + 1 :]
    background_context = "\n".join(get_code_message_from_features(background_features))

    # Build conversation: [rejection_prompt, message_prompt, keep_context, remove_context]
    messages = [
        ChatCompletionSystemMessageParam(
            role="system",
            content=dedent("""\
                You are part of an LLM Coding Assistant, designed to answer questions and
                complete tasks for developers. Specifically, you generate examples of
                interactions where the user has not provided enough context to fulfill the
                query. You will be shown an example query, some background code which will
                be included, and some target code which is NOT be included.

                Pretend you haven't seen the target code, and tell the user what additional
                information you'll need in order to fulfill the task. Take a deep breath,
                focus, and then complete your task by following this procedure:

                1. Read the USER QUERY (below) carefully. Consider the steps involved in
                   completing it.
                2. Read the BACKROUND CONTEXT (below that) carefully. Consider how it
                   contributes to completing the task.
                3. Read the TARGET CONTEXT (below that) carefully. Consider how it
                   contributes to completing the task.
                4. Think of a short (1-sentence) explanation of why the TARGET CONTEXT is
                   required to complete the task.
                5. Return a ~1 paragraph message to the user explaining why the BACKGROUND
                   CONTEXT is not sufficient to answer the question.

                REMEMBER:
                * Don't reference TARGET CONTEXT specifically. Answer as if you've never
                  seen it, you just know you're missing something essential.
                * Return #5 (your response to the user) as a single paragraph, without
                  preamble, notes, extra spacing or additional commentary.
            """),
        ),
        ChatCompletionUserMessageParam(
            role="user", content=f"USER QUERY:\n{sample.message_prompt}"
        ),
        ChatCompletionSystemMessageParam(
            role="system",
            content=f"BACKGROUND CONTEXT:\n{background_context}",
        ),
        ChatCompletionSystemMessageParam(
            role="system",
            content=f"TARGET CONTEXT:\n{target_context}",
        ),
    ]

    # Ask gpt-4 to generate rejection prompt
    llm_api_handler = python_client.session.ctx.llm_api_handler
    llm_api_handler.initialize_client()
    llm_response = await llm_api_handler.call_llm_api(
        messages=messages,
        model=python_client.session.ctx.config.model,
        stream=False,
    )
    message = (llm_response.choices[0].message.content) or ""

    # Ask user to review and accept/reject
    print("Sample Prompt:", sample.message_prompt)
    print("Removed context:", target)
    print("Generated reason:", message)
    print("Press ENTER to accept, or type a new reason to reject.")
    response = input()
    if response:
        message = response
    if not message:
        raise SampleError("No rejection reason provided. Aborting.")

    # Create and return a duplicate/udpated sample
    new_sample = Sample(**attr.asdict(sample))
    new_sample.context = [str(f) for f in background_features]
    new_sample.id = uuid4().hex
    new_sample.title = f"{sample.title} [REMOVE {target.path.name}]"
    new_sample.message_edit = message
    new_sample.diff_edit = ""

    return new_sample
