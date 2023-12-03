from abc import ABC, abstractmethod

from mentat.code_feature import CodeFeature


class FeatureFilter(ABC):
    """
    Tools to pare down a list of Features to a final list to be put in an LLMs context.
    Despite the name they may not be pure filters:
    * New CodeFeatures may be introduced by splitting Features into intervals.
    * The CodeFeatures may be reordered by priority in future steps.

    A feature filter may want more information than the list of features and user prompt. If so it
    can get it from the config or have the information passed into its constructor.
    """

    @abstractmethod
    async def filter(
        self,
        features: list[CodeFeature],
    ) -> list[CodeFeature]:
        raise NotImplementedError()
