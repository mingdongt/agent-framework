from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class PropertyResult:
    passed: bool
    message: str
    repro_snippet: str | None = None


class SpecProperty(ABC):
    """A property derived from a spec. Subclasses set `spec` + `name` + `description`."""

    spec: str = ""
    name: str = ""
    description: str = ""

    def __init__(self) -> None:
        if not self.spec or not self.name:
            raise ValueError(
                f"{type(self).__name__} must define class attrs `spec` and `name`"
            )

    @property
    def full_id(self) -> str:
        return f"{self.spec}/{self.name}"

    @abstractmethod
    def run(self, adapter: Any) -> PropertyResult: ...
