# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path

import pytest

from af_watch.corpus_loader import CorpusLoader
from af_watch.exceptions import CorpusError


def _write_corpus(root: Path) -> None:
    (root / "domain_map").mkdir(parents=True)
    (root / "domain_map" / "microsoft__agent-framework.md").write_text(
        "# microsoft/agent-framework — Domain Map\n\nArchitecture: dual-language SDK.\n",
        encoding="utf-8",
    )
    (root / "comparison_matrix").mkdir()
    (root / "comparison_matrix" / "features.yaml").write_text(
        '''mcp_x:
  description: "x"
  frameworks:
    microsoft/agent-framework:
      status: not_implemented
    google/adk-python:
      status: implemented
''',
        encoding="utf-8",
    )
    (root / "industry_intel").mkdir()
    (root / "industry_intel" / "2026-05.md").write_text(
        "## 2026-05-15: Anthropic dev day\n- MCP 2025-06 draft\n",
        encoding="utf-8",
    )


def test_loads_all_three(tmp_path: Path) -> None:
    _write_corpus(tmp_path)
    loader = CorpusLoader(corpus_dir=tmp_path)
    snapshot = loader.load()
    assert "microsoft/agent-framework" in snapshot.domain_maps
    assert "mcp_x" in snapshot.comparison_matrix
    assert len(snapshot.industry_intel) >= 1


def test_query_feature_lag(tmp_path: Path) -> None:
    _write_corpus(tmp_path)
    loader = CorpusLoader(corpus_dir=tmp_path)
    snapshot = loader.load()
    gaps = snapshot.feature_gaps(home="microsoft/agent-framework")
    assert "mcp_x" in [g.feature for g in gaps]


def test_missing_corpus_dir(tmp_path: Path) -> None:
    with pytest.raises(CorpusError, match="corpus directory"):
        CorpusLoader(corpus_dir=tmp_path / "nope").load()


def test_malformed_yaml(tmp_path: Path) -> None:
    (tmp_path / "domain_map").mkdir(parents=True)
    (tmp_path / "comparison_matrix").mkdir()
    (tmp_path / "comparison_matrix" / "features.yaml").write_text("{ not: valid: yaml }\n")
    (tmp_path / "industry_intel").mkdir()
    with pytest.raises(CorpusError, match=r"features\.yaml"):
        CorpusLoader(corpus_dir=tmp_path).load()
