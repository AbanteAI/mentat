from mentat.code_feature import CodeFeature
from mentat.embeddings import get_feature_similarity_scores
from mentat.feature_filters.feature_filter import FeatureFilter


class EmbeddingSimilarityFilter(FeatureFilter):
    def __init__(self, query: str, loading_multiplier: float = 0.0):
        self.query = query
        self.loading_multiplier = loading_multiplier

    async def score(
        self,
        features: list[CodeFeature],
    ) -> list[tuple[CodeFeature, float]]:
        if self.query == "":
            return [(f, 0.0) for f in features]

        sim_scores = await get_feature_similarity_scores(
            self.query, features, self.loading_multiplier
        )
        features_scored = zip(features, sim_scores)
        return sorted(features_scored, key=lambda x: x[1])

    async def filter(
        self,
        features: list[CodeFeature],
    ) -> list[CodeFeature]:
        if self.query == "":
            return features
        return [f for f, _ in await self.score(features)]
