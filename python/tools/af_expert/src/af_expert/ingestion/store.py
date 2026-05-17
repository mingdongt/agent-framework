from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from af_expert.config import _state_dir


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    number       INTEGER,
    title        TEXT,
    body         TEXT,
    diff         TEXT,
    author       TEXT,
    state        TEXT,
    labels       TEXT,
    created_at   TEXT,
    updated_at   TEXT,
    closed_at    TEXT,
    merged_at    TEXT,
    url          TEXT,
    raw          TEXT,
    ingested_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repo, kind, number)
);

CREATE INDEX IF NOT EXISTS idx_events_repo_kind_created ON events (repo, kind, created_at);
CREATE INDEX IF NOT EXISTS idx_events_repo_kind_merged ON events (repo, kind, merged_at);

CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    title, body, diff, labels,
    content='events', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, title, body, diff, labels)
    VALUES (new.id, new.title, new.body, new.diff, new.labels);
END;

CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, body, diff, labels)
    VALUES('delete', old.id, old.title, old.body, old.diff, old.labels);
END;

CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, body, diff, labels)
    VALUES('delete', old.id, old.title, old.body, old.diff, old.labels);
    INSERT INTO events_fts(rowid, title, body, diff, labels)
    VALUES (new.id, new.title, new.body, new.diff, new.labels);
END;
"""


@dataclass
class EventRecord:
    repo: str
    kind: str  # "issue" | "pr" | "release"
    number: int | None
    title: str
    body: str
    author: str
    state: str
    labels: list[str]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    merged_at: datetime | None = None
    diff: str | None = None
    url: str = ""
    raw: dict[str, Any] | None = None


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class EventStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path else _state_dir() / "events.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row

    def ensure_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def insert(self, rec: EventRecord) -> None:
        payload = {
            "repo": rec.repo,
            "kind": rec.kind,
            "number": rec.number,
            "title": rec.title,
            "body": rec.body,
            "diff": rec.diff,
            "author": rec.author,
            "state": rec.state,
            "labels": json.dumps(rec.labels),
            "created_at": _iso(rec.created_at),
            "updated_at": _iso(rec.updated_at),
            "closed_at": _iso(rec.closed_at),
            "merged_at": _iso(rec.merged_at),
            "url": rec.url,
            "raw": json.dumps(rec.raw or {}),
        }
        self._conn.execute(
            """
            INSERT INTO events (repo, kind, number, title, body, diff, author, state, labels,
                                created_at, updated_at, closed_at, merged_at, url, raw)
            VALUES (:repo, :kind, :number, :title, :body, :diff, :author, :state, :labels,
                    :created_at, :updated_at, :closed_at, :merged_at, :url, :raw)
            ON CONFLICT(repo, kind, number) DO UPDATE SET
                title=excluded.title,
                body=excluded.body,
                diff=excluded.diff,
                author=excluded.author,
                state=excluded.state,
                labels=excluded.labels,
                updated_at=excluded.updated_at,
                closed_at=excluded.closed_at,
                merged_at=excluded.merged_at,
                url=excluded.url,
                raw=excluded.raw
            """,
            payload,
        )
        self._conn.commit()

    def query_recent_prs(
        self,
        repo: str,
        since: datetime,
        only_merged: bool = True,
    ) -> Iterator[dict[str, Any]]:
        where = ["repo = ?", "kind = 'pr'", "updated_at >= ?"]
        params: list[Any] = [repo, since.isoformat()]
        if only_merged:
            where.append("state = 'merged'")
        sql = f"SELECT * FROM events WHERE {' AND '.join(where)} ORDER BY merged_at DESC"
        for row in self._conn.execute(sql, params):
            yield dict(row)

    def query_closed_issues(
        self,
        repo: str,
        before: datetime,
        labels_any_of: list[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        where = ["repo = ?", "kind = 'issue'", "state = 'closed'", "closed_at <= ?"]
        params: list[Any] = [repo, before.isoformat()]
        if labels_any_of:
            # naive substring match within JSON-encoded labels
            label_clause = " OR ".join(["labels LIKE ?"] * len(labels_any_of))
            where.append(f"({label_clause})")
            params.extend([f'%"{lab}"%' for lab in labels_any_of])
        sql = f"SELECT * FROM events WHERE {' AND '.join(where)} ORDER BY closed_at DESC"
        for row in self._conn.execute(sql, params):
            yield dict(row)

    def fts_search(self, query: str, limit: int = 50) -> Iterator[dict[str, Any]]:
        sql = """
            SELECT e.* FROM events e
            JOIN events_fts ON events_fts.rowid = e.id
            WHERE events_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        for row in self._conn.execute(sql, (query, limit)):
            yield dict(row)

    def close(self) -> None:
        self._conn.close()
