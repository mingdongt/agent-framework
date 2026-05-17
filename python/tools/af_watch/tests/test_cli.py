# Copyright (c) Microsoft. All rights reserved.

from pathlib import Path

from af_watch.cli import build_parser, cmd_init


def test_parser_known_subcommands() -> None:
    parser = build_parser()
    ns = parser.parse_args(["init"])
    assert ns.cmd == "init"
    ns = parser.parse_args(["run", "--window", "7d"])
    assert ns.cmd == "run"
    assert ns.window == "7d"
    ns = parser.parse_args(["report"])
    assert ns.cmd == "report"
    ns = parser.parse_args(["open"])
    assert ns.cmd == "open"
    ns = parser.parse_args(["corpus", "refresh"])
    assert ns.cmd == "corpus"
    assert ns.corpus_action == "refresh"
    assert ns.stale_days == 28


def test_init_creates_config_skeleton(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AF_WATCH_HOME", str(tmp_path))
    code = cmd_init([])
    assert code == 0
    assert (tmp_path / "config.toml").exists()
    # af-watch uses claude CLI auth (no API key); sample config contains github_token
    assert "github_token" in (tmp_path / "config.toml").read_text(encoding="utf-8")


def test_init_does_not_overwrite_existing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AF_WATCH_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text('github_token = "existing"\n')
    code = cmd_init([])
    assert code == 0
    assert "existing" in (tmp_path / "config.toml").read_text(encoding="utf-8")
