"""SQLite adapter for the local demo's shared submission and job state."""

import os
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import time
from uuid import UUID, uuid4

from .contracts import CreateRun, CreateSubmission, EvaluationResult, Run, RunError, RunSpec, Submission

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id),
    idempotency_key TEXT NOT NULL UNIQUE,
    request TEXT NOT NULL,
    spec TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    lease_until REAL,
    lease_token TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    result TEXT,
    error TEXT
);
"""


class IdempotencyConflict(Exception):
    pass


@dataclass(frozen=True)
class Claim:
    spec: RunSpec
    token: str


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            yield db

    def create_submission(self, data: CreateSubmission) -> Submission:
        item = Submission(**data.model_dump(), id=uuid4(), created_at=datetime.now(UTC))
        with self.connect() as db:
            db.execute("INSERT INTO submissions VALUES (?, ?)", (str(item.id), item.model_dump_json()))
        return item

    def list_submissions(self) -> list[Submission]:
        with self.connect() as db:
            rows = db.execute("SELECT record FROM submissions ORDER BY rowid DESC").fetchall()
        return [Submission.model_validate_json(row["record"]) for row in rows]

    def create_run(self, data: CreateRun, key: str, rules_version: str) -> Run | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT * FROM runs WHERE idempotency_key = ?", (key,)).fetchone()
            if previous:
                if CreateRun.model_validate_json(previous["request"]) != data:
                    raise IdempotencyConflict
                return read_run(previous)
            row = db.execute("SELECT record FROM submissions WHERE id = ?", (str(data.submission_id),)).fetchone()
            if row is None:
                return None
            submission = Submission.model_validate_json(row["record"])
            run_id = uuid4()
            spec = RunSpec(
                run_id=run_id, submission_id=submission.id, dataset_id=data.dataset_id,
                baseline_id=submission.source.baseline_id, rules_version=rules_version,
            )
            now = datetime.now(UTC)
            db.execute(
                """INSERT INTO runs (id, submission_id, idempotency_key, request, spec, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'QUEUED', ?)""",
                (str(run_id), str(submission.id), key, data.model_dump_json(), spec.model_dump_json(), now.isoformat()),
            )
        return Run(
            id=run_id, submission_id=submission.id, dataset_id=data.dataset_id,
            rules_version=rules_version, status="QUEUED", created_at=now,
        )

    def get_run(self, run_id: UUID) -> tuple[Run, EvaluationResult | None] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id = ?", (str(run_id),)).fetchone()
        if row is None:
            return None
        result = EvaluationResult.model_validate_json(row["result"]) if row["result"] else None
        return read_run(row), result

    def claim(self, lease_seconds: float = 120) -> Claim | None:
        now = time()
        token = str(uuid4())
        expired = RunError(code="LEASE_EXPIRED", message="评测进程中断，重试次数已用完")
        with self.connect() as db:
            db.execute(
                """UPDATE runs SET status = 'FAILED', error = ?, lease_token = NULL, lease_until = NULL
                   WHERE status = 'RUNNING' AND lease_until <= ? AND attempts >= 2""",
                (expired.model_dump_json(), now),
            )
            row = db.execute(
                """UPDATE runs SET status = 'RUNNING', lease_token = ?, lease_until = ?, attempts = attempts + 1
                   WHERE id = (
                       SELECT id FROM runs WHERE status = 'QUEUED'
                           OR (status = 'RUNNING' AND lease_until <= ? AND attempts < 2)
                       ORDER BY created_at, id LIMIT 1
                   ) RETURNING spec""",
                (token, now + lease_seconds, now),
            ).fetchone()
        return Claim(RunSpec.model_validate_json(row["spec"]), token) if row else None

    def finish(self, claim: Claim, outcome: EvaluationResult | RunError) -> bool:
        result = isinstance(outcome, EvaluationResult)
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE runs SET status = ?, result = ?, error = ?, lease_token = NULL, lease_until = NULL
                   WHERE id = ? AND status = 'RUNNING' AND lease_token = ? AND lease_until > ?""",
                ("SUCCEEDED" if result else "FAILED",
                 outcome.model_dump_json() if result else None,
                 None if result else outcome.model_dump_json(),
                 str(claim.spec.run_id), claim.token, time()),
            )
            return cursor.rowcount == 1


def read_run(row: sqlite3.Row) -> Run:
    spec = RunSpec.model_validate_json(row["spec"])
    return Run(
        id=spec.run_id, submission_id=spec.submission_id, dataset_id=spec.dataset_id,
        rules_version=spec.rules_version, status=row["status"], created_at=row["created_at"],
        error=RunError.model_validate_json(row["error"]) if row["error"] else None,
    )


def local_database() -> Path:
    return Path(os.environ.get("AGENTQUANT_DB", ".agentquant/local.sqlite3"))
