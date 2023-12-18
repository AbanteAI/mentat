from typing import Optional

from mentat.code_feature import CodeFeature
from mentat.errors import ContextSizeInsufficient, ModelError
from mentat.feature_filters.embedding_similarity_filter import EmbeddingSimilarityFilter
from mentat.feature_filters.feature_filter import FeatureFilter
from mentat.feature_filters.llm_feature_filter import LLMFeatureFilter
from mentat.feature_filters.truncate_filter import TruncateFilter
from mentat.session_context import SESSION_CONTEXT


class DefaultFilter(FeatureFilter):
    def __init__(
        self,
        max_tokens: int,
        use_llm: bool = False,
        user_prompt: Optional[str] = None,
        expected_edits: Optional[list[str]] = None,
        loading_multiplier: float = 0.0,
    ):
        self.max_tokens = max_tokens
        self.use_llm = use_llm
        self.user_prompt = user_prompt or ""
        self.expected_edits = expected_edits
        self.loading_multiplier = loading_multiplier

    async def filter(self, features: list[CodeFeature]) -> list[CodeFeature]:
        ctx = SESSION_CONTEXT.get()

        if ctx.config.auto_context and self.user_prompt != "":
            features = await EmbeddingSimilarityFilter(
                self.user_prompt, (0.5 if self.use_llm else 1) * self.loading_multiplier
            ).filter(features)

        if self.use_llm:
            try:
                features = await LLMFeatureFilter(
                    self.max_tokens,
                    self.user_prompt,
                    self.expected_edits,
                    (0.5 if self.user_prompt != "" else 1) * self.loading_multiplier,
                ).filter(features)
            except (ModelError, ContextSizeInsufficient):
                ctx.stream.send(
                    "Feature-selection LLM response invalid. Using TruncateFilter"
                    " instead."
                )
                features = await TruncateFilter(
                    self.max_tokens, ctx.config.model
                ).filter(features)
        else:
            features = await TruncateFilter(self.max_tokens, ctx.config.model).filter(
                features
            )

        return features
