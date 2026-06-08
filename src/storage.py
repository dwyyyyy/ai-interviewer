from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_INTERVIEW_DB_PATH = Path("data/interview_memory.sqlite3")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _loads(text: str | None, fallback: Any) -> Any:
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


class InterviewStore:
    """Single-table persistence for the latest demo interview.

    The runtime still keeps structured memory in InterviewMemory. SQLite is a
    compact persistence snapshot: one row per session, JSON fields for turns,
    direction scores, final_profile_json and report_json.

    final_profile_json is the long-term machine-readable candidate profile.
    report_json/readable_report is a presentation artifact for the current demo.
    """

    def __init__(self, db_path: Path = DEFAULT_INTERVIEW_DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interview_memory (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    jd_text TEXT NOT NULL,
                    resume_text TEXT NOT NULL,
                    jd_structured_json TEXT NOT NULL,
                    resume_structured_json TEXT NOT NULL,
                    match_json TEXT NOT NULL,
                    role_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    pre_interview_brief_json TEXT NOT NULL,
                    turns_json TEXT NOT NULL,
                    direction_scores_json TEXT NOT NULL,
                    final_profile_json TEXT,
                    report_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def start_latest_session(
        self,
        *,
        jd_text: str,
        resume_text: str,
        jd_structured: dict[str, Any],
        resume_structured: dict[str, Any],
        match_analysis: dict[str, Any],
        role: dict[str, Any],
        plan: dict[str, Any],
        pre_interview_brief: dict[str, Any],
    ) -> str:
        session_id = "latest"
        now = _now()
        with self._connect() as conn:
            conn.execute("DELETE FROM interview_memory WHERE id = ?", (session_id,))
            conn.execute(
                """
                INSERT INTO interview_memory (
                    id, status, jd_text, resume_text, jd_structured_json,
                    resume_structured_json, match_json, role_json, plan_json,
                    pre_interview_brief_json, turns_json, direction_scores_json,
                    final_profile_json, report_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    "running",
                    jd_text,
                    resume_text,
                    _json(jd_structured),
                    _json(resume_structured),
                    _json(match_analysis),
                    _json(role),
                    _json(plan),
                    _json(pre_interview_brief),
                    _json([]),
                    _json([]),
                    None,
                    None,
                    now,
                    now,
                ),
            )
            conn.commit()
        return session_id

    def add_turn(self, session_id: str, turn: dict[str, Any]) -> None:
        with self._connect() as conn:
            row = self._get_session(conn, session_id)
            turns = _loads(row["turns_json"], [])
            turns.append(turn)
            conn.execute(
                """
                UPDATE interview_memory
                SET turns_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json(turns), _now(), session_id),
            )
            conn.commit()

    def add_direction_score(self, session_id: str, score: dict[str, Any]) -> None:
        with self._connect() as conn:
            row = self._get_session(conn, session_id)
            scores = _loads(row["direction_scores_json"], [])
            scores.append(score)
            conn.execute(
                """
                UPDATE interview_memory
                SET direction_scores_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json(scores), _now(), session_id),
            )
            conn.commit()

    def finish_session(
        self,
        session_id: str,
        *,
        final_profile: dict[str, Any],
        report: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            self._get_session(conn, session_id)
            conn.execute(
                """
                UPDATE interview_memory
                SET final_profile_json = ?, report_json = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json(final_profile), _json(report), "finished", _now(), session_id),
            )
            conn.commit()

    def latest_overview(self) -> dict[str, Any]:
        with self._connect() as conn:
            session = conn.execute(
                """
                SELECT id, status, created_at, updated_at, turns_json,
                       direction_scores_json, final_profile_json
                FROM interview_memory
                WHERE id = ?
                """,
                ("latest",),
            ).fetchone()
        turns = _loads(session["turns_json"], []) if session else []
        scores = _loads(session["direction_scores_json"], []) if session else []
        return {
            "has_session": session is not None,
            "session": {
                "id": session["id"],
                "status": session["status"],
                "created_at": session["created_at"],
                "updated_at": session["updated_at"],
            } if session else None,
            "turn_count": len(turns),
            "direction_score_count": len(scores),
            "has_profile": bool(session and session["final_profile_json"]),
            "db_path": str(self.db_path),
        }

    def latest_turns(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            session = conn.execute(
                "SELECT turns_json FROM interview_memory WHERE id = ?",
                ("latest",),
            ).fetchone()
        return _loads(session["turns_json"], []) if session else []

    def _get_session(self, conn: sqlite3.Connection, session_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM interview_memory WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Interview session not found: {session_id}")
        return row
