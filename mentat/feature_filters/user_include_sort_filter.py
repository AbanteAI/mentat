from mentat.code_feature import CodeFeature
from mentat.feature_filters.feature_filter import FeatureFilter


class UserIncludedSortFilter(FeatureFilter):
    async def filter(self, features: list[CodeFeature]) -> list[CodeFeature]:
        return sorted(features, key=lambda x: x.user_included, reverse=True)
