"""
Takas kümeleme çalıştırmaları ve küme performans etiketleri (SQLite).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from fundamental_db import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS takas_cluster_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    method TEXT NOT NULL,
    n_symbols INTEGER,
    smart_cluster_id INTEGER,
    n_noise INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_takas_cluster_run_date_method
ON takas_cluster_runs(run_date, method);

CREATE TABLE IF NOT EXISTS takas_cluster_members (
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    is_smart_cluster INTEGER NOT NULL DEFAULT 0,
    analyzer_score REAL,
    features_json TEXT,
    PRIMARY KEY (run_id, symbol),
    FOREIGN KEY (run_id) REFERENCES takas_cluster_runs(id)
);

CREATE TABLE IF NOT EXISTS takas_cluster_performance (
    run_date TEXT NOT NULL,
    method TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    horizon_days INTEGER NOT NULL,
    mean_return_pct REAL,
    n_symbols INTEGER,
    labeled_at TEXT,
    PRIMARY KEY (run_date, method, cluster_id, horizon_days)
);
"""


def init_takas_cluster_tables() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _get_run_id(conn: sqlite3.Connection, run_date: str, method: str) -> Optional[int]:
    cur = conn.execute(
        "SELECT id FROM takas_cluster_runs WHERE run_date = ? AND method = ?",
        (run_date, method),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def save_cluster_run(
    run_date: str,
    method: str,
    symbols: List[str],
    cluster_ids: List[int],
    smart_cluster_id: int,
    is_smart_flags: List[int],
    analyzer_scores: List[float],
    features_by_symbol: Dict[str, Dict[str, float]],
    n_noise: int = 0,
) -> int:
    from datetime import datetime

    init_takas_cluster_tables()
    conn = sqlite3.connect(DB_PATH)
    try:
        rid_old = _get_run_id(conn, run_date, method)
        if rid_old is not None:
            conn.execute("DELETE FROM takas_cluster_members WHERE run_id = ?", (rid_old,))
            conn.execute("DELETE FROM takas_cluster_runs WHERE id = ?", (rid_old,))
        conn.execute(
            """INSERT INTO takas_cluster_runs
            (run_date, method, n_symbols, smart_cluster_id, n_noise, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                run_date,
                method,
                len(symbols),
                smart_cluster_id,
                n_noise,
                datetime.now().isoformat(),
            ),
        )
        run_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        for i, sym in enumerate(symbols):
            conn.execute(
                """INSERT INTO takas_cluster_members
                (run_id, symbol, cluster_id, is_smart_cluster, analyzer_score, features_json)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    sym.upper(),
                    int(cluster_ids[i]),
                    int(is_smart_flags[i]),
                    float(analyzer_scores[i]) if i < len(analyzer_scores) else None,
                    json.dumps(features_by_symbol.get(sym.upper(), features_by_symbol.get(sym, {}))),
                ),
            )
        conn.commit()
        return run_id
    finally:
        conn.close()


def get_latest_cluster_for_symbol(symbol: str, method: str = "kmeans") -> Optional[Dict[str, Any]]:
    init_takas_cluster_tables()
    sym = symbol.upper()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            """
            SELECT m.cluster_id, m.is_smart_cluster, m.analyzer_score, r.run_date, r.smart_cluster_id
            FROM takas_cluster_members m
            JOIN takas_cluster_runs r ON r.id = m.run_id
            WHERE m.symbol = ? AND r.method = ?
            ORDER BY r.run_date DESC, r.id DESC
            LIMIT 1
            """,
            (sym, method),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "cluster_id": row[0],
            "is_smart_cluster": bool(row[1]),
            "analyzer_score": row[2],
            "run_date": row[3],
            "smart_cluster_id": row[4],
        }
    finally:
        conn.close()


def get_run_members(run_date: str, method: str) -> List[Dict[str, Any]]:
    init_takas_cluster_tables()
    conn = sqlite3.connect(DB_PATH)
    try:
        rid = _get_run_id(conn, run_date, method)
        if rid is None:
            return []
        cur = conn.execute(
            "SELECT symbol, cluster_id, is_smart_cluster, analyzer_score FROM takas_cluster_members WHERE run_id = ?",
            (rid,),
        )
        return [
            {"symbol": r[0], "cluster_id": r[1], "is_smart_cluster": r[2], "analyzer_score": r[3]}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def save_cluster_performance(
    run_date: str,
    method: str,
    cluster_id: int,
    horizon_days: int,
    mean_return_pct: float,
    n_symbols: int,
) -> None:
    from datetime import datetime

    init_takas_cluster_tables()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO takas_cluster_performance
            (run_date, method, cluster_id, horizon_days, mean_return_pct, n_symbols, labeled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                run_date,
                method,
                cluster_id,
                horizon_days,
                mean_return_pct,
                n_symbols,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def export_training_rows(method: str = "kmeans"):
    """Küme atamaları + (varsa) küme performansı — eğitim verisi birleştirmesi için."""
    import pandas as pd

    init_takas_cluster_tables()
    conn = sqlite3.connect(DB_PATH)
    try:
        q = """
        SELECT r.run_date, m.symbol, m.cluster_id, m.is_smart_cluster, m.analyzer_score, m.features_json,
               p.horizon_days, p.mean_return_pct
        FROM takas_cluster_runs r
        JOIN takas_cluster_members m ON m.run_id = r.id
        LEFT JOIN takas_cluster_performance p
          ON p.run_date = r.run_date AND p.method = r.method AND p.cluster_id = m.cluster_id
        WHERE r.method = ?
        ORDER BY r.run_date DESC
        """
        return pd.read_sql_query(q, conn, params=(method,))
    finally:
        conn.close()
