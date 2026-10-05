"""Approved-only versioned bank import, isolated from the legacy training store."""

import json
import sqlite3
import os
from contextlib import closing
from pathlib import Path

from database.database import DATABASE_PATH, get_connection
from services.question_validator import load_taxonomy, validate_candidate


def import_questions(candidates: list[dict], *, database_path: str | Path) -> dict:
    """Import an approved batch atomically; reject real math_ai.db in V0.8B.

    This v2 bank has no route into legacy questions/attempts. Activating v2 training
    needs the separately reviewed taxonomy migration; never reinterpret old K005.
    """
    path = Path(database_path).resolve()
    if path == DATABASE_PATH.resolve() or (path.exists() and DATABASE_PATH.exists() and os.path.samefile(path, DATABASE_PATH)):
        raise ValueError("V0.8B 禁止导入真实 math_ai.db，请使用隔离数据库。")
    result = {"inserted": 0, "skipped": 0, "rejected": 0, "errors": []}
    accepted = []
    for candidate in candidates:
        validation = validate_candidate(candidate)
        if candidate.get("quality_status") != "approved" or not validation["can_approve"]:
            result["rejected"] += 1
            result["errors"].append({"id": candidate.get("id"), "reasons":
                                     validation["errors"] + validation["warnings"]
                                     + (["仅允许 approved"] if candidate.get("quality_status") != "approved" else [])})
        else:
            accepted.append(candidate)
    if not accepted:
        return result
    try:
        with closing(get_connection(path)) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("""CREATE TABLE IF NOT EXISTS bank_knowledge_points (
                    taxonomy_version TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL,
                    prerequisite_ids TEXT NOT NULL, PRIMARY KEY (taxonomy_version, id))""")
                connection.execute("""CREATE TABLE IF NOT EXISTS approved_question_bank (
                    id TEXT PRIMARY KEY, taxonomy_version TEXT NOT NULL,
                    primary_knowledge_point_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    quality_status TEXT NOT NULL CHECK (quality_status = 'approved'),
                    payload TEXT NOT NULL,
                    FOREIGN KEY (taxonomy_version, primary_knowledge_point_id)
                        REFERENCES bank_knowledge_points(taxonomy_version, id))""")
                taxonomy = load_taxonomy()
                connection.executemany("""INSERT INTO bank_knowledge_points VALUES (?, ?, ?, ?)
                                         ON CONFLICT(taxonomy_version, id) DO NOTHING""",
                                       [("function_v2", point["id"], point["name"], json.dumps(point["prerequisite_ids"]))
                                        for point in taxonomy["knowledge_points"]])
                for candidate in accepted:
                    same_id = connection.execute("SELECT fingerprint FROM approved_question_bank WHERE id = ?",
                                                 (candidate["id"],)).fetchone()
                    if same_id and same_id["fingerprint"] != candidate["fingerprint"]:
                        raise ValueError("相同题号对应不同内容，整批回滚")
                    exists = connection.execute("SELECT id FROM approved_question_bank WHERE fingerprint = ?",
                                                (candidate["fingerprint"],)).fetchone()
                    if exists:
                        result["skipped"] += 1
                        continue
                    connection.execute("""INSERT INTO approved_question_bank
                        (id, taxonomy_version, primary_knowledge_point_id, fingerprint, quality_status, payload)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                                       (candidate["id"], candidate["taxonomy_version"],
                                        candidate["primary_knowledge_point_id"], candidate["fingerprint"],
                                        "approved", json.dumps(candidate, ensure_ascii=False)))
                    result["inserted"] += 1
    except (sqlite3.Error, ValueError) as error:
        result["inserted"] = result["skipped"] = 0
        result["errors"].append({"id": None, "reasons": [f"整批回滚：{type(error).__name__}"]})
    return result


def get_approved_questions(knowledge_point_id: str, *, database_path: str | Path) -> list[dict]:
    """Approved-only v2 bank read boundary for future training/recommendation adapters."""
    with closing(get_connection(database_path, read_only=True)) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                  ("approved_question_bank",)).fetchone():
            return []
        rows = connection.execute("""SELECT payload FROM approved_question_bank
            WHERE taxonomy_version = ? AND primary_knowledge_point_id = ? AND quality_status = ?
            ORDER BY id""", ("function_v2", knowledge_point_id, "approved")).fetchall()
    return [json.loads(row["payload"]) for row in rows]
