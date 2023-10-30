import json
from textwrap import dedent
from typing import Optional, cast

import openai

from mentat.code_feature import CodeFeature, CodeMessageLevel
from mentat.llm_api import count_tokens
from mentat.session_context import SESSION_CONTEXT

"""
Context selection is similar to the Knapsack Problem: given a set of items (features),
and a knapsack (context size), choose the best subset of items that fit. In our case we
can also select which level include. We implement two methods:

- Greedy: add features one-by-one, at the most detailed level possible, until the maximum
    token limit is reached.

- LLM: create a full-context of code using the greedy method, then ask the LLM to select
    only the relevant features. Return its output, up to the token limit.
"""


def select_features_greedy(
    features: list[CodeFeature],
    max_tokens: int,
    model: str = "gpt-4",
    levels: list[CodeMessageLevel] = [],
) -> list[CodeFeature]:
    """Use the greedy method to return a subset of features max_tokens long"""
    output = list[CodeFeature]()
    remaining_tokens = max_tokens
    for feature in features:
        _levels = list(set(levels) | {feature.level})
        _levels = sorted(list(_levels), key=lambda v: v.rank)
        for level in _levels:
            feature.level = level
            if feature.count_tokens(model) <= remaining_tokens:
                output.append(feature)
                remaining_tokens -= feature.count_tokens(model)
                break

    return output


feature_selection_model = "gpt-4"
feature_selection_max_tokens = 8192
feature_selection_temperature = 0.5
feature_selection_response_buffer = 500
feature_selection_prompt = dedent("""\
    You are part of an automated coding system. 
    Below you will see the line 'User Query:', followed by a user query, followed by the line 'Code Files:' and then a pre-selected subset of a codebase.
    Your job is to select portions of the code which are relevant to answering that query.
    The process after you will read the lines code you select, and then return a plaintext plan of action and a list of Code Edits.
    {{training_prompt}}
    Each item in the Code Files below will include a relative path and line numbers.
    Identify lines of code which are relevant to the query.
    Return a json-serializable list of relevant items following the same format you receive: <rel_path>:<start_line>-<end_line>,<start_line>-<end_line>.
    It's important to include lines which would be edited in order to generate the answer as well as lines which are required to understand the context.
    It's equally important to exclude irrelevant code, as it has a negative impact on the system performance and cost.
    For example: if a question requires creating a new method related to a class, and the method uses an attribute of that
    class, include the location for the edit as well as where the attribute is defined. If a typing system is used, include
    the type definition as well, and the location of the expected import.
    Make sure your response is valid json, for example:
    ["path/to/file1.py:1-10,53-60", "path/to/file2.py:10-20"]
    """)
training_prompt = (
    "You are currently being used to generate benchmarking data, so you'll be shown"
    " those Code Edits as well in order to maximize your performance."
)


async def select_features_llm(
    features: list[CodeFeature],
    max_tokens: int,
    model: str = "gpt-4",
    levels: list[CodeMessageLevel] = [],
    user_prompt: str = "",
    expected_edits: Optional[list[str]] = None,  # For benchmarks/training
) -> list[CodeFeature]:
    session_context = SESSION_CONTEXT.get()
    git_root = session_context.git_root

    # Preselect as many features as fit in the context window
    user_prompt_tokens = count_tokens(user_prompt, model)
    system_prompt = feature_selection_prompt.format(
        training_prompt=training_prompt if expected_edits else ""
    )
    system_prompt_tokens = count_tokens(system_prompt, feature_selection_model)
    preselect_max_tokens = (
        feature_selection_max_tokens
        - system_prompt_tokens
        - user_prompt_tokens
        - feature_selection_response_buffer
    )
    preselected_features = select_features_greedy(
        features, preselect_max_tokens, feature_selection_model, levels
    )

    # Ask the model to return only relevant features
    content_message = [
        "User Query:",
        user_prompt,
        "",
        "Code Files:",
    ]
    for feature in preselected_features:
        content_message += feature.get_code_message()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": "\n".join(content_message)},
    ]
    response = await openai.ChatCompletion.acreate(  # type: ignore
        model=model,
        messages=messages,
        temperature=feature_selection_temperature,
    )

    # Create output features from the response
    message = cast(str, response["choices"][0]["message"]["content"])  # type: ignore
    try:
        selected_refs = json.loads(message)
    except json.JSONDecodeError:
        raise ValueError(f"The response is not valid json: {message}")
    postselected_features = [CodeFeature(git_root / p) for p in selected_refs]
    for out_feat in postselected_features:
        # Match with corresponding inputs
        matching_inputs = [
            in_feat
            for in_feat in features
            if in_feat.path == out_feat.path
            and any(
                i_in.intersects(i_out)
                for i_in in in_feat.intervals
                for i_out in out_feat.intervals
            )
        ]
        if len(matching_inputs) == 0:
            raise ValueError(f"No input feature found for llm-selected {out_feat}")
        # Copy metadata
        out_feat.user_included = any(f.user_included for f in matching_inputs)
        diff = any(f.diff for f in matching_inputs)
        name = any(f.name for f in matching_inputs)
        if diff:
            out_feat.diff = next(f.diff for f in matching_inputs if f.diff)
        if name:
            out_feat.name = next(f.name for f in matching_inputs if f.name)

    # Greedy again to enforce max_tokens
    return select_features_greedy(postselected_features, max_tokens, model)
