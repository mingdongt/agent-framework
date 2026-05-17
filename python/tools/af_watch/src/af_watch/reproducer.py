# Copyright (c) Microsoft. All rights reserved.

import logging
import subprocess
from pathlib import Path
from typing import Callable

from af_watch.models import Opportunity

_LOG = logging.getLogger(__name__)


_RunnerSig = Callable[[list[str], Path, int], tuple[int, str, str]]


def _default_runner(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str, str]:
    proc = subprocess.run(  # noqa: S603 — script content is operator-trusted within home workspace
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


class Reproducer:
    def __init__(
        self,
        *,
        workspace_base: Path,
        home_repo: str,
        timeout_seconds: int = 60,
        runner: _RunnerSig | None = None,
    ) -> None:
        self._base = workspace_base
        self._home = home_repo
        self._timeout = timeout_seconds
        self._runner: _RunnerSig = runner if runner is not None else _default_runner

    def attempt(self, opp: Opportunity, *, repro_script: str) -> Opportunity:
        if not opp.target.startswith(self._home + ":"):
            opp.repro_status = "not_attempted"
            return opp

        workspace_name = self._home.replace("/", "__")
        workspace = self._base / workspace_name
        if not workspace.exists():
            opp.repro_status = "not_attempted"
            return opp

        artifact_dir = workspace / ".af_watch_repro" / opp.id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        script_path = artifact_dir / "repro.py"
        script_path.write_text(repro_script, encoding="utf-8")

        try:
            returncode, _stdout, _stderr = self._runner(
                ["python", str(script_path)], workspace, self._timeout,
            )
        except TimeoutError:
            opp.repro_status = "attempted_timeout"
            return opp
        except Exception as exc:
            _LOG.warning("repro execution error: %s", exc)
            opp.repro_status = "attempted_failed"
            return opp

        if returncode != 0:
            opp.repro_status = "confirmed"
            opp.repro_artifact = str(script_path)
        else:
            opp.repro_status = "attempted_failed"
        return opp
