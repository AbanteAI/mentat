from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Self

from mentat.code_changes.abstract.abstract_change import AbstractChange
from mentat.code_file_manager import CodeFileManager


class ConcreteChange(ABC):
    @abstractmethod
    @classmethod
    def from_abstract_change(cls, abstract_change: AbstractChange) -> Self:
        pass

    @abstractmethod
    @classmethod
    async def stream_and_parse_llm_response(
        cls, response: AsyncGenerator[Any, None], code_file_manager: CodeFileManager
    ) -> Self:
        pass

    @abstractmethod
    def to_abstract_change(self) -> AbstractChange:
        pass
