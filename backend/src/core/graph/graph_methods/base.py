from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable


class BaseGraph(ABC):
    """Shared minimal contract for graph variants in this domain."""

    @abstractmethod
    def edges_from(self, node_id: str) -> Iterable[object]:
        raise NotImplementedError
