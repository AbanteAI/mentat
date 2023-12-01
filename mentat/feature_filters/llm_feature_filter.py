import json
from pathlib import Path
from timeit import default_timer
from typing import Optional, Set

from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
)

from mentat.code_feature import (
    CodeFeature,
    CodeMessageLevel,
    get_code_message_from_features,
)
from mentat.errors import ModelError, UserError
from mentat.feature_filters.feature_filter import FeatureFilter
from mentat.feature_filters.truncate_filter import TruncateFilter
from mentat.include_files import get_code_features_for_path
from mentat.llm_api_handler import count_tokens, model_context_size, prompt_tokens
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT


class LLMFeatureFilter(FeatureFilter):
    feature_selection_prompt_path = Path("feature_selection_prompt.txt")

    def __init__(
        self,
        max_tokens: int,
        user_prompt: Optional[str] = None,
        levels: list[CodeMessageLevel] = [],
        expected_edits: Optional[list[str]] = None,
        loading_multiplier: float = 0.0,
    ):
        self.max_tokens = max_tokens
        self.user_prompt = user_prompt or ""
        self.levels = levels
        self.expected_edits = expected_edits
        self.loading_multiplier = loading_multiplier

    async def filter(
        self,
        features: list[CodeFeature],
    ) -> list[CodeFeature]:
        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        config = session_context.config
        cost_tracker = session_context.cost_tracker
        llm_api_handler = session_context.llm_api_handler

        # Preselect as many features as fit in the context window
        model = config.feature_selection_model
        context_size = model_context_size(model)
        if context_size is None:
            raise UserError(
                "Unknown context size for feature selection model: "
                f"{config.feature_selection_model}"
            )
        system_prompt = read_prompt(self.feature_selection_prompt_path)
        system_prompt_tokens = count_tokens(
            system_prompt, config.feature_selection_model, full_message=True
        )
        user_prompt_tokens = count_tokens(self.user_prompt, model, full_message=True)
        expected_edits_tokens = (
            0
            if not self.expected_edits
            else count_tokens("\n".join(self.expected_edits), model, full_message=True)
        )
        preselect_max_tokens = (
            context_size
            - system_prompt_tokens
            - user_prompt_tokens
            - expected_edits_tokens
            - config.token_buffer
        )
        truncate_filter = TruncateFilter(
            preselect_max_tokens, model, levels=self.levels
        )
        preselected_features = await truncate_filter.filter(features)

        # Ask the model to return only relevant features
        content_message = [
            "User Query:",
            self.user_prompt,
            "",
            "Code Files:",
        ]
        content_message += get_code_message_from_features(preselected_features)
        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionSystemMessageParam(
                role="system", content="\n".join(content_message)
            ),
        ]
        if self.expected_edits:
            messages.append(
                ChatCompletionSystemMessageParam(
                    role="system", content=f"Expected Edits:\n{self.expected_edits}"
                )
            )

        if self.loading_multiplier:
            stream.send(
                "Asking LLM to filter out irrelevant context...",
                channel="loading",
                progress=50 * self.loading_multiplier,
            )
        selected_refs = list[Path]()
        n_tries = 3
        for i in range(n_tries):
            start_time = default_timer()
            message = (
                (await llm_api_handler.call_llm_api(messages, model, stream=False))
                .choices[0]
                .message.content
            ) or ""

            tokens = prompt_tokens(messages, model)
            response_tokens = count_tokens(message, model, full_message=True)
            cost_tracker.log_api_call_stats(
                tokens,
                response_tokens,
                model,
                default_timer() - start_time,
            )
            try:
                response = json.loads(message)  # type: ignore
                selected_refs = [Path(r) for r in response]
                break
            except json.JSONDecodeError:
                # TODO: Update Loader
                if i == n_tries - 1:
                    raise ModelError(f"The response is not valid json: {message}")
        if self.loading_multiplier:
            stream.send(
                "Parsing LLM response...",
                channel="loading",
                progress=50 * self.loading_multiplier,
            )

        parsed_features: Set[CodeFeature] = set()
        for selected_ref in selected_refs:
            _parsed_features = get_code_features_for_path(
                path=selected_ref, cwd=session_context.cwd
            )
            parsed_features.update(_parsed_features)

        # parsed_features, _ = get_include_files(selected_refs, [])
        # postselected_features = [feature for features in parsed_features.values() for feature in features]

        for parsed_feature in parsed_features:
            # Match with corresponding inputs
            matching_inputs = [
                in_feat
                for in_feat in features
                if in_feat.path == parsed_feature.path
                and in_feat.interval.intersects(parsed_feature.interval)
            ]
            if len(matching_inputs) == 0:
                raise ModelError(
                    f"No input feature found for llm-selected {parsed_feature}"
                )
            # Copy metadata
            parsed_feature.user_included = any(f.user_included for f in matching_inputs)
            diff = any(f.diff for f in matching_inputs)
            name = any(f.name for f in matching_inputs)
            if diff:
                parsed_feature.diff = next(f.diff for f in matching_inputs if f.diff)
            if name:
                parsed_feature.name = next(f.name for f in matching_inputs if f.name)

        # Greedy again to enforce max_tokens
        truncate_filter = TruncateFilter(self.max_tokens, config.model)
        return await truncate_filter.filter(parsed_features)
