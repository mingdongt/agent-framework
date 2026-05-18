from pathlib import Path
from unittest.mock import MagicMock

from project_expert.config import Config, ProjectConfig
from project_expert.models import IssueEntry
from project_expert.state import State
from project_expert.tools.issues_tool import projects_issues


def test_issues_returns_results(tmp_path: Path) -> None:
    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[ProjectConfig(repo="foo/bar", tier="mirror_only")],
        settings=dict(mirrors_dir=str(tmp_path / "m"), kg_dir=str(tmp_path / "kg"), index_dir=str(tmp_path / "idx")),
    )
    state = State.load(tmp_path / "state.json")
    fake_client = MagicMock()
    fake_client.search.return_value = [
        IssueEntry(number=1, title="bug", url="x", state="open"),
        IssueEntry(number=2, title="bug2", url="y", state="open"),
    ]
    out = projects_issues(config=cfg, state=state, issues_client=fake_client, project="foo/bar", query="bug")
    assert isinstance(out, list)
    assert len(out) == 2


def test_issues_unknown_project(tmp_path: Path) -> None:
    cfg = Config(
        llm=dict(provider="anthropic", model="x", api_key_env="X"),
        projects=[],
        settings=dict(mirrors_dir=str(tmp_path / "m"), kg_dir=str(tmp_path / "kg"), index_dir=str(tmp_path / "idx")),
    )
    state = State.load(tmp_path / "state.json")
    out = projects_issues(config=cfg, state=state, issues_client=MagicMock(), project="nope/nope", query="x")
    assert out["error"] == "project_not_tracked"
