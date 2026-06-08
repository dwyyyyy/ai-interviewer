from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_BANK_PATH = Path("data/question_bank.json")
DEFAULT_DB_PATH = Path("data/question_bank.sqlite3")


def load_question_bank(path: Path = DEFAULT_BANK_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def rebuild_fts_index(
    bank_path: Path = DEFAULT_BANK_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    bank = load_question_bank(bank_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS question_bank")
        conn.execute("DROP TABLE IF EXISTS question_bank_fts")
        conn.execute(
            """
            CREATE TABLE question_bank (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE question_bank_fts USING fts5(
                id UNINDEXED,
                content,
                tokenize='unicode61'
            )
            """
        )
        for item in bank:
            payload = json.dumps(item, ensure_ascii=False)
            content = _document_text(item)
            conn.execute("INSERT INTO question_bank(id, payload) VALUES (?, ?)", (item["id"], payload))
            conn.execute("INSERT INTO question_bank_fts(id, content) VALUES (?, ?)", (item["id"], content))
        conn.commit()


def retrieve_questions(
    query: str,
    top_k: int = 3,
    db_path: Path = DEFAULT_DB_PATH,
    bank_path: Path = DEFAULT_BANK_PATH,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        rebuild_fts_index(bank_path=bank_path, db_path=db_path)

    fts_query = _to_fts_query(query)
    if not fts_query:
        return load_question_bank(bank_path)[:top_k]

    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT qb.payload
                FROM question_bank_fts fts
                JOIN question_bank qb ON qb.id = fts.id
                WHERE question_bank_fts MATCH ?
                ORDER BY bm25(question_bank_fts)
                LIMIT ?
                """,
                (fts_query, top_k),
            ).fetchall()
    except sqlite3.OperationalError:
        rows = []

    if not rows:
        return _keyword_fallback(query, top_k, load_question_bank(bank_path))
    return [json.loads(row[0]) for row in rows]


def _document_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            str(item.get("topic", "")),
            str(item.get("difficulty", "")),
            str(item.get("question_template", "")),
            " ".join(item.get("evaluation_points", [])),
            " ".join(item.get("follow_ups", [])),
        ]
    )


def _to_fts_query(query: str) -> str:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_+#.-]*|[\u4e00-\u9fff]{2,}", query.lower())
    tokens = [token.replace('"', "") for token in tokens if len(token) >= 2]
    # OR keeps recall high for mixed Chinese/English technical queries.
    return " OR ".join(f'"{token}"' for token in tokens[:12])


def _keyword_fallback(query: str, top_k: int, bank: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tokens = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_+#.-]*|[\u4e00-\u9fff]{2,}", query.lower()))
    scored = []
    for item in bank:
        text = _document_text(item).lower()
        score = sum(1 for token in tokens if token in text)
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for score, item in scored[:top_k] if score > 0] or bank[:top_k]
