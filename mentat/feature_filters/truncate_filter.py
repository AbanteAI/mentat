from mentat.code_feature import CodeFeature, CodeMessageLevel
from mentat.feature_filters.feature_filter import FeatureFilter


class TruncateFilter(FeatureFilter):
    def __init__(
        self,
        max_tokens: int,
        model: str = "gpt-4",
        code_map: bool = False,
        respect_user_include: bool = True,
    ):
        self.max_tokens = max_tokens
        self.model = model
        self.code_map = code_map
        self.respect_user_include = respect_user_include

    async def filter(
        self,
        features: list[CodeFeature],
    ) -> list[CodeFeature]:
        """Truncate the features to max_token tokens."""
        levels = [CodeMessageLevel.FILE_NAME]
        if self.code_map:
            levels = [
                CodeMessageLevel.CMAP_FULL,
                CodeMessageLevel.CMAP,
            ] + levels
        output = list[CodeFeature]()
        remaining_tokens = self.max_tokens
        for feature in features:
            _levels = list(set(levels) | {feature.level})
            _levels = sorted(list(_levels), key=lambda v: v.rank)
            for level in _levels:
                feature.level = level
                if (
                    feature.count_tokens(self.model) <= remaining_tokens
                    or self.respect_user_include
                    and feature.user_included
                ):
                    output.append(feature)
                    remaining_tokens -= feature.count_tokens(self.model)
                    break

        return output
