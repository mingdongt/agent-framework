from __future__ import annotations

import pytest

from af_expert.framework_adapters.base import FrameworkAdapter


def test_framework_adapter_has_required_attrs() -> None:
    """Subclasses must define `framework` and at least one simulate_* method."""
    with pytest.raises(TypeError):
        FrameworkAdapter()  # ABC cannot be instantiated directly


def test_concrete_adapter_works() -> None:
    class FakeAdapter(FrameworkAdapter):
        framework = "fake/repo"

        def simulate_mcp_initialize(self, payload):
            return {"ok": True}

        def simulate_mcp_oauth_refresh_request(self, payload):
            return {"omits_resource": True}

        def simulate_mcp_tool_result(self, payload):
            return {"valid": True}

    a = FakeAdapter()
    assert a.framework == "fake/repo"
    assert a.simulate_mcp_initialize({"x": 1}) == {"ok": True}
