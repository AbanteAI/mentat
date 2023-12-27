from typing import Iterable

from mentat.code_feature import CodeFeature
from mentat.feature_filters.feature_filter import FeatureFilter


class TruncateFilter(FeatureFilter):
    def __init__(
        self,
        max_tokens: int,
        model: str = "gpt-4",
    ):
        self.max_tokens = max_tokens
        self.model = model

    async def filter(
        self,
        features: Iterable[CodeFeature],
    ) -> list[CodeFeature]:
        """Truncate the features to max_token tokens."""
        output = list[CodeFeature]()
        remaining_tokens = self.max_tokens
        for feature in features:
            if feature.count_tokens(self.model) <= remaining_tokens:
                output.append(feature)
                remaining_tokens -= feature.count_tokens(self.model)

        return output
