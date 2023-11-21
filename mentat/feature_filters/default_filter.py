from typing import Optional

from mentat.code_feature import CodeFeature, CodeMessageLevel
from mentat.errors import ModelError
from mentat.feature_filters.embedding_similarity_filter import EmbeddingSimilarityFilter
from mentat.feature_filters.feature_filter import FeatureFilter
from mentat.feature_filters.llm_feature_filter import LLMFeatureFilter
from mentat.feature_filters.truncate_filter import TruncateFilter
from mentat.feature_filters.user_include_sort_filter import UserIncludedSortFilter
from mentat.session_context import SESSION_CONTEXT


class DefaultFilter(FeatureFilter):
    def __init__(
        self,
        max_tokens: int,
        code_map: bool = False,
        use_llm: bool = False,
        user_prompt: Optional[str] = None,
        expected_edits: Optional[list[str]] = None,
        loading_multiplier: float = 0.0,
    ):
        self.max_tokens = max_tokens
        self.code_map = code_map
        self.use_llm = use_llm
        self.user_prompt = user_prompt or ""
        self.levels = [CodeMessageLevel.FILE_NAME]
        if self.code_map:
            self.levels = [
                CodeMessageLevel.CMAP_FULL,
                CodeMessageLevel.CMAP,
            ] + self.levels
        self.expected_edits = expected_edits
        self.loading_multiplier = loading_multiplier

    async def filter(self, features: list[CodeFeature]) -> list[CodeFeature]:
        session = SESSION_CONTEXT.get()
        stream = session.stream
        model = session.config.model

        if self.user_prompt != "":
            features = await EmbeddingSimilarityFilter(
                self.user_prompt, (0.5 if self.use_llm else 1) * self.loading_multiplier
            ).filter(features)
        # python sorts are stable (even with reversed=true) so the two groups: included and not included
        # will maintain their relative orders
        features = await UserIncludedSortFilter().filter(features)
        if self.use_llm:
            try:
                features = await LLMFeatureFilter(
                    self.max_tokens,
                    self.user_prompt,
                    self.levels,
                    self.expected_edits,
                    (0.5 if self.user_prompt != "" else 1) * self.loading_multiplier,
                ).filter(features)
            except ModelError:
                stream.send(
                    "Feature-selection LLM response invalid. Using TruncateFilter"
                    " instead."
                )
                features = await TruncateFilter(
                    self.max_tokens, model, self.levels, True
                ).filter(features)
        else:
            features = await TruncateFilter(
                self.max_tokens, model, self.levels, True
            ).filter(features)
        return features
