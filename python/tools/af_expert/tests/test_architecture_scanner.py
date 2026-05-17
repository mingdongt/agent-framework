from __future__ import annotations

from pathlib import Path

import pytest

from af_expert.architecture.scanner import (
    FileInventory,
    scan_repo_locally,
)


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Create a fake repo tree that looks like a Python agent framework."""
    repo = tmp_path / "fake-agent"
    (repo / "src" / "fake_agent").mkdir(parents=True)
    (repo / "src" / "fake_agent" / "__init__.py").write_text("")
    (repo / "src" / "fake_agent" / "chat_client.py").write_text(
        "class ChatClient:\n    pass\n"
    )
    (repo / "src" / "fake_agent" / "_anthropic.py").write_text(
        "class AnthropicChatClient:\n    pass\n"
    )
    (repo / "src" / "fake_agent" / "_openai.py").write_text(
        "class OpenAIChatClient:\n    pass\n"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_chat.py").write_text("def test_x(): pass\n")
    (repo / "README.md").write_text("# Fake Agent\n\nA test repo.\n")
    (repo / "pyproject.toml").write_text('[project]\nname = "fake-agent"\n')
    return repo


def test_scan_finds_python_modules(fake_repo: Path) -> None:
    inv = scan_repo_locally(fake_repo)
    assert isinstance(inv, FileInventory)
    assert any("chat_client.py" in f for f in inv.source_files)
    assert any("_anthropic.py" in f for f in inv.source_files)


def test_scan_classifies_provider_files(fake_repo: Path) -> None:
    inv = scan_repo_locally(fake_repo)
    # Files matching provider name patterns get classified
    assert "anthropic" in inv.provider_files
    assert "openai" in inv.provider_files


def test_scan_excludes_tests_from_source(fake_repo: Path) -> None:
    inv = scan_repo_locally(fake_repo)
    assert not any("test_chat.py" in f for f in inv.source_files)
    assert any("test_chat.py" in f for f in inv.test_files)


def test_scan_returns_readme_text(fake_repo: Path) -> None:
    inv = scan_repo_locally(fake_repo)
    assert "Fake Agent" in inv.readme_excerpt


def test_scan_handles_missing_readme(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    (repo / "src" / "x").mkdir(parents=True)
    (repo / "src" / "x" / "main.py").write_text("")
    inv = scan_repo_locally(repo)
    assert inv.readme_excerpt == ""


def test_scan_caps_file_counts(tmp_path: Path) -> None:
    """If a repo has 10000 files, we keep only the most relevant subset."""
    repo = tmp_path / "huge"
    (repo / "src").mkdir(parents=True)
    for i in range(500):
        (repo / "src" / f"file_{i}.py").write_text("")
    inv = scan_repo_locally(repo, max_source_files=100)
    assert len(inv.source_files) == 100
