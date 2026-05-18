from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from af_expert.architecture.briefing import render_briefing
from af_expert.architecture.scanner import scan_repo_locally
from af_expert.config import _state_dir
from af_expert.llm import LLM
from af_expert.state import atomic_write


log = logging.getLogger(__name__)


@dataclass
class RefreshResult:
    repo: str
    success: bool
    briefing_path: Path
    error: str | None = None


def repo_briefing_path(repo: str) -> Path:
    safe = repo.replace("/", "__")
    return _state_dir() / "repos" / safe / "architecture.md"


def _clone_repo_shallow(repo: str, dest: Path) -> Path:
    url = f"https://github.com/{repo}.git"
    cmd = ["git", "clone", "--depth", "1", "--filter=blob:none", "--single-branch", url, str(dest)]
    log.info("cloning %s into %s", repo, dest)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git clone failed for {repo}: rc={proc.returncode} stderr={proc.stderr[:500]}"
        )
    return dest


def refresh_one_repo(repo: str, *, llm: LLM) -> RefreshResult:
    briefing_path = repo_briefing_path(repo)
    briefing_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="af-expert-clone-"))
    try:
        clone_dir = tmp_dir / repo.split("/")[-1]
        try:
            _clone_repo_shallow(repo, clone_dir)
        except Exception as e:
            log.warning("Clone failed for %s: %s", repo, e)
            stub = (
                f"# {repo}\n\n"
                f"**Briefing unavailable — clone failed.**\n\nError: {e}\n"
            )
            atomic_write(briefing_path, stub)
            return RefreshResult(repo=repo, success=False, briefing_path=briefing_path, error=str(e))

        inventory = scan_repo_locally(clone_dir)
        briefing_md = render_briefing(repo=repo, inventory=inventory, llm=llm)
        atomic_write(briefing_path, briefing_md)

        return RefreshResult(repo=repo, success=True, briefing_path=briefing_path)
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
