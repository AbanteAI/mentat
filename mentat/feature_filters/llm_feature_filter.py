import json
from pathlib import Path
from typing import Optional

from mentat.code_feature import (
    CodeFeature,
    CodeMessageLevel,
    get_code_message_from_features,
)
from mentat.errors import UserError
from mentat.feature_filters.feature_filter import FeatureFilter
from mentat.feature_filters.truncate_filter import TruncateFilter
from mentat.include_files import get_include_files
from mentat.llm_api import call_llm_api_sync, count_tokens, model_context_size
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT


class LLMFeatureFilter(FeatureFilter):
    feature_selection_prompt_path = Path("feature_selection_prompt.txt")
    feature_selection_response_buffer = 500

    def __init__(
        self,
        max_tokens: int,
        model: str = "gpt-4",
        user_prompt: Optional[str] = None,
        levels: list[CodeMessageLevel] = [],
        expected_edits: Optional[list[str]] = None,
    ):
        self.max_tokens = max_tokens
        self.user_prompt = user_prompt or ""
        self.levels = levels
        self.expected_edits = expected_edits

    async def filter(
        self,
        features: list[CodeFeature],
    ) -> list[CodeFeature]:
        session_context = SESSION_CONTEXT.get()
        config = session_context.config

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
            system_prompt, config.feature_selection_model
        )
        user_prompt_tokens = count_tokens(self.user_prompt, model)
        expected_edits_tokens = (
            0
            if not self.expected_edits
            else count_tokens("\n".join(self.expected_edits), model)
        )
        preselect_max_tokens = (
            context_size
            - system_prompt_tokens
            - user_prompt_tokens
            - expected_edits_tokens
            - self.feature_selection_response_buffer
        )
        truncate_filter = TruncateFilter(
            preselect_max_tokens, model=model, levels=self.levels
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
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": "\n".join(content_message)},
        ]
        if self.expected_edits:
            messages.append(
                {"role": "system", "content": f"Expected Edits:\n{self.expected_edits}"}
            )
        message = await call_llm_api_sync(model, messages)
        try:
            selected_refs = json.loads(message)  # type: ignore
        except json.JSONDecodeError:
            raise ValueError(f"The response is not valid json: {message}")
        parsed_features, _ = get_include_files(selected_refs, [])
        postselected_features = [
            feature for features in parsed_features.values() for feature in features
        ]

        for out_feat in postselected_features:
            # Match with corresponding inputs
            matching_inputs = [
                in_feat
                for in_feat in features
                if in_feat.path == out_feat.path
                and in_feat.interval.intersects(out_feat.interval)
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
        truncate_filter = TruncateFilter(self.max_tokens, model=model)
        return await truncate_filter.filter(postselected_features)
