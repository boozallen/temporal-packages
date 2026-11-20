# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from temporalio import activity

_DEFAULT_DB_PATH = os.path.join(tempfile.gettempdir(), "foundry_provenance.db")
_SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text()


@dataclass
class ProvenanceRecord:
    id: int
    workflow_id: str
    file_reference: str
    step_name: str
    outcome: str
    timestamp: str


_initialized_dbs: set[str] = set()


def init_provenance_db(db_path: str | None = None) -> None:
    """Initialize the provenance database and table. Safe to call multiple times."""
    path = db_path or _DEFAULT_DB_PATH
    if path in _initialized_dbs:
        return
    conn = sqlite3.connect(path)
    try:
        conn.execute(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    _initialized_dbs.add(path)


@activity.defn
def update_provenance(
    workflow_id: str,
    file_reference: str,
    step_name: str,
    outcome: str,
    db_path: str | None = None,
) -> None:
    """Write a provenance record to the SQLite database."""
    path = db_path or _DEFAULT_DB_PATH
    init_provenance_db(path)
    conn = sqlite3.connect(path)
    try:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT INTO provenance (workflow_id, file_reference, step_name, outcome, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (workflow_id, file_reference, step_name, outcome, ts),
        )
        conn.commit()
    finally:
        conn.close()


def get_provenance(
    workflow_id: str,
    db_path: str | None = None,
) -> list[ProvenanceRecord]:
    """Query provenance records by workflow ID, ordered by timestamp."""
    path = db_path or _DEFAULT_DB_PATH
    init_provenance_db(path)
    conn = sqlite3.connect(path)
    try:
        cursor = conn.execute(
            "SELECT id, workflow_id, file_reference, step_name, outcome, timestamp "
            "FROM provenance WHERE workflow_id = ? ORDER BY timestamp",
            (workflow_id,),
        )
        return [ProvenanceRecord(*row) for row in cursor.fetchall()]
    finally:
        conn.close()
