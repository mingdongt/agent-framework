from __future__ import annotations

import pytest

from af_expert.spec_corpus.base import (
    PropertyResult,
    SpecProperty,
)


class _GoodProperty(SpecProperty):
    spec = "test"
    name = "always_passes"
    description = "trivially passes"

    def run(self, adapter):
        return PropertyResult(passed=True, message="ok")


class _BadProperty(SpecProperty):
    spec = "test"
    name = "always_fails"
    description = "trivially fails"

    def run(self, adapter):
        return PropertyResult(passed=False, message="boom", repro_snippet="assert 1 == 2")


def test_property_metadata_required() -> None:
    p = _GoodProperty()
    assert p.spec == "test"
    assert p.name == "always_passes"
    assert p.full_id == "test/always_passes"


def test_property_run_returns_passing_result() -> None:
    p = _GoodProperty()
    result = p.run(adapter=None)
    assert result.passed is True
    assert result.message == "ok"


def test_property_run_returns_failing_result_with_repro() -> None:
    p = _BadProperty()
    result = p.run(adapter=None)
    assert result.passed is False
    assert result.repro_snippet == "assert 1 == 2"


def test_property_subclass_must_define_spec_and_name() -> None:
    class Incomplete(SpecProperty):
        description = "missing fields"
        def run(self, adapter):
            return PropertyResult(passed=True, message="")

    with pytest.raises(ValueError):
        Incomplete()
