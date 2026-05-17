# Copyright (c) Microsoft. All rights reserved.

import json
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from af_fix.models import Issue, IssueRef, ScoreResult


class TodoItem(BaseModel):
    repo: str
    number: int
    score: int
    reason: str
    suggested_files: list[str] = []
    title: str = ""
    body: str = ""


class TodoList(BaseModel):
    generated_at: datetime
    items: list[TodoItem]


_MD_HEADER = """\
# af-fix triage results — {ts}

Edit this file: check `[x]` the issues you want af-fix to attempt.
Delete or leave unchecked any you want to skip. Then run:

    af-fix execute --from {md_path}

---

"""

_MD_ITEM = """\
- [ ] {repo}#{number} (score: {score}) — {reason}
      Suggested files: {files}
      URL: https://github.com/{repo}/issues/{number}

"""


def _format_iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def render_markdown(
    *,
    scores: list[ScoreResult],
    issues_by_key: dict[str, Issue],
    generated_at: datetime,
    md_path: str = "~/.af-fix/todolist-<TIMESTAMP>.md",
) -> str:
    sorted_scores = sorted(scores, key=lambda s: s.score, reverse=True)
    body = _MD_HEADER.format(ts=_format_iso(generated_at), md_path=md_path)
    for s in sorted_scores:
        files = ", ".join(s.suggested_files) if s.suggested_files else "(none)"
        body += _MD_ITEM.format(
            repo=s.ref.repo,
            number=s.ref.number,
            score=s.score,
            reason=s.reason,
            files=files,
        )
    return body


def save_todolist(
    *,
    scores: list[ScoreResult],
    issues_by_key: dict[str, Issue],
    generated_at: datetime,
    out_dir: Path,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = generated_at.strftime("%Y-%m-%dT%H%M%SZ")
    md_path = out_dir / f"todolist-{ts}.md"
    json_path = out_dir / f"todolist-{ts}.json"

    md = render_markdown(
        scores=scores,
        issues_by_key=issues_by_key,
        generated_at=generated_at,
        md_path=str(md_path),
    )
    md_path.write_text(md, encoding="utf-8")

    sorted_scores = sorted(scores, key=lambda s: s.score, reverse=True)
    items: list[TodoItem] = []
    for s in sorted_scores:
        issue = issues_by_key.get(s.ref.key)
        items.append(TodoItem(
            repo=s.ref.repo,
            number=s.ref.number,
            score=s.score,
            reason=s.reason,
            suggested_files=s.suggested_files,
            title=issue.title if issue else "",
            body=issue.body if issue else "",
        ))
    todolist = TodoList(generated_at=generated_at, items=items)
    json_path.write_text(
        json.dumps(todolist.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return md_path, json_path


_CHECKED_RE = re.compile(
    r"^\s*-\s*\[(?:x|X)\]\s*(?P<repo>[^/\s#]+/[^#\s]+)#(?P<number>\d+)",
    re.MULTILINE,
)


def parse_checked_items(markdown: str) -> list[IssueRef]:
    out: list[IssueRef] = []
    for m in _CHECKED_RE.finditer(markdown):
        out.append(IssueRef(repo=m.group("repo"), number=int(m.group("number"))))
    return out


def load_todolist_json(path: Path) -> TodoList:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return TodoList.model_validate(raw)
