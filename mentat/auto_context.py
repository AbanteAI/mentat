import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, cast

import openai

from mentat.code_feature import (
    CodeFeature,
    CodeMessageLevel,
    get_code_message_from_features,
)
from mentat.errors import UserError
from mentat.include_files import get_include_files
from mentat.llm_api import (
    count_tokens,
    model_context_size,
    raise_if_in_test_environment,
)
from mentat.prompts.prompts import read_prompt
from mentat.session_context import SESSION_CONTEXT


class FeatureSelector(ABC):
    """
    Context selection is similar to the Knapsack Problem: given a set of items (features),
    and a knapsack (context size), choose the best subset of items that fit. In our case we
    can also select which level include. We implement two methods:

    - Greedy: add features one-by-one, at the most detailed level possible, until the maximum
        token limit is reached.

    - LLM: create a full-context of code using the greedy method, then ask the LLM to select
        only the relevant features. Return its output, up to the token limit.
    """

    selector_name: str

    def __init_subclass__(cls, selector_name: str):
        cls.selector_name = selector_name

    @abstractmethod
    async def select(
        self,
        features: list[CodeFeature],
        max_tokens: int,
        model: str,
        levels: list[CodeMessageLevel] = [],
        user_prompt: Optional[str] = None,
        expected_edits: Optional[list[str]] = None,
    ) -> list[CodeFeature]:
        """Select a subset of features that fit in max_tokens"""
        raise NotImplementedError()


class GreedyFeatureSelector(FeatureSelector, selector_name="greedy"):
    async def select(
        self,
        features: list[CodeFeature],
        max_tokens: int,
        model: str = "gpt-4",
        levels: list[CodeMessageLevel] = [],
        user_prompt: Optional[str] = None,
        expected_edits: Optional[list[str]] = None,
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


class LLMFeatureSelector(FeatureSelector, selector_name="llm"):
    feature_selection_prompt_path = Path("feature_selection_prompt.txt")
    feature_selection_response_buffer = 500

    async def call_llm_api(self, model: str, messages: list[dict[str, str]]) -> str:
        raise_if_in_test_environment()

        session_context = SESSION_CONTEXT.get()
        config = session_context.config

        response = await openai.ChatCompletion.acreate(  # type: ignore
            model=model,
            messages=messages,
            temperature=config.temperature,
        )

        # Create output features from the response
        return cast(str, response["choices"][0]["message"]["content"])  # type: ignore

    async def select(
        self,
        features: list[CodeFeature],
        max_tokens: int,
        model: str = "gpt-4",
        levels: list[CodeMessageLevel] = [],
        user_prompt: Optional[str] = None,
        expected_edits: Optional[list[str]] = None,
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
        if user_prompt is None:
            user_prompt = ""
        user_prompt_tokens = count_tokens(user_prompt, model)
        expected_edits_tokens = (
            0 if not expected_edits else count_tokens("\n".join(expected_edits), model)
        )
        preselect_max_tokens = (
            context_size
            - system_prompt_tokens
            - user_prompt_tokens
            - expected_edits_tokens
            - self.feature_selection_response_buffer
        )
        greedy_selector = GreedyFeatureSelector()
        preselected_features = await greedy_selector.select(
            features, preselect_max_tokens, model, levels
        )

        # Ask the model to return only relevant features
        content_message = [
            "User Query:",
            user_prompt,
            "",
            "Code Files:",
        ]
        content_message += get_code_message_from_features(preselected_features)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": "\n".join(content_message)},
        ]
        if expected_edits:
            messages.append(
                {"role": "system", "content": f"Expected Edits:\n{expected_edits}"}
            )
        message = await self.call_llm_api(model, messages)
        try:
            selected_refs = json.loads(message)
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
        return await greedy_selector.select(postselected_features, max_tokens, model)


def get_feature_selector(use_llm: bool) -> FeatureSelector:
    if use_llm:
        return LLMFeatureSelector()
    else:
        return GreedyFeatureSelector()
