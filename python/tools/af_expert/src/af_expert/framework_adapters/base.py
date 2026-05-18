from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FrameworkAdapter(ABC):
    """Minimum interface a framework must implement to be testable by S5."""

    framework: str = ""  # owner/repo

    @abstractmethod
    def simulate_mcp_initialize(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def simulate_mcp_oauth_refresh_request(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def simulate_mcp_tool_result(self, payload: dict[str, Any]) -> dict[str, Any]: ...
