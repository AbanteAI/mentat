import json
from pathlib import Path
from typing import Optional, Set

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.completion_create_params import ResponseFormat

from mentat.code_feature import CodeFeature, get_code_message_from_features
from mentat.errors import ModelError, PathValidationError, UserError
from mentat.feature_filters.feature_filter import FeatureFilter
from mentat.feature_filters.truncate_filter import TruncateFilter
from mentat.include_files import get_code_features_for_path
from mentat.llm_api_handler import count_tokens, model_context_size
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT


class LLMFeatureFilter(FeatureFilter):
    feature_selection_prompt_path = Path("feature_selection_prompt.txt")

    def __init__(
        self,
        max_tokens: int,
        user_prompt: Optional[str] = None,
        expected_edits: Optional[list[str]] = None,
    ):
        self.max_tokens = max_tokens
        self.user_prompt = user_prompt or ""
        self.expected_edits = expected_edits

    async def filter(
        self,
        features: list[CodeFeature],
    ) -> list[CodeFeature]:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        llm_api_handler = session_context.llm_api_handler

        stream.send(None, channel="loading")

        # Preselect as many features as fit in the context window
        model = config.feature_selection_model
        context_size = model_context_size(model)
        if context_size is None:
            raise UserError("Unknown context size for feature selection model: " f"{config.feature_selection_model}")
        context_size = min(context_size, config.llm_feature_filter)
        system_prompt = read_prompt(self.feature_selection_prompt_path)
        system_prompt_tokens = count_tokens(system_prompt, config.feature_selection_model, full_message=True)
        user_prompt_tokens = count_tokens(self.user_prompt, model, full_message=True)
        expected_edits_tokens = (
            0 if not self.expected_edits else count_tokens("\n".join(self.expected_edits), model, full_message=True)
        )
        preselect_max_tokens = (
            context_size - system_prompt_tokens - user_prompt_tokens - expected_edits_tokens - config.token_buffer
        )
        truncate_filter = TruncateFilter(preselect_max_tokens, model)
        preselected_features = await truncate_filter.filter(features)

        # Ask the model to return only relevant features
        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionSystemMessageParam(
                role="system",
                content="\n".join(["CODE FILES:"] + get_code_message_from_features(preselected_features)),
            ),
            ChatCompletionUserMessageParam(role="user", content=f"USER QUERY: {self.user_prompt}"),
        ]
        if self.expected_edits:
            messages.append(
                ChatCompletionAssistantMessageParam(role="assistant", content=f"Expected Edits:\n{self.expected_edits}")
            )
        messages.append(
            ChatCompletionSystemMessageParam(
                role="system",
                content=(
                    "Now, identify the CODE FILES that are relevant to answering the"
                    " USER QUERY, Return a dict of {path: reason} for each file you"
                    " identify as relevant. e.g. {'src/main.js': 'Create new file',"
                    " 'public/index.html': 'Import main.js'}"
                ),
            )
        )
        selected_refs = list[Path]()
        llm_response = await llm_api_handler.call_llm_api(
            messages=messages,
            model=model,
            stream=False,
            response_format=ResponseFormat(type="json_object"),
        )
        message = llm_response.text
        stream.send(None, channel="loading", terminate=True)

        # Parse response into features
        try:
            response = json.loads(message)  # type: ignore
            selected_refs = [Path(r) for r in response]
        except json.JSONDecodeError:
            raise ModelError(f"The response is not valid json: {message}")
        postselected_features: Set[CodeFeature] = set()
        for selected_ref in selected_refs:
            try:
                parsed_features = get_code_features_for_path(path=selected_ref, cwd=session_context.cwd)
                for feature in parsed_features:
                    assert any(
                        in_feat.path == feature.path and in_feat.interval.intersects for in_feat in preselected_features
                    )
                    postselected_features.add(feature)
            except (PathValidationError, AssertionError):
                stream.send(
                    f"LLM selected invalid path: {selected_ref}, skipping.",
                    style="warning",
                )

        # Truncate again to enforce max_tokens
        truncate_filter = TruncateFilter(self.max_tokens, config.model)
        return await truncate_filter.filter(postselected_features)
