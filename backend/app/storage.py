"""SQLite persistence. Immediate transactions serialize stock and crew allocations."""
import json
import os
import sqlite3
from contextlib import contextmanager
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets(sid TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workspaces(sid TEXT NOT NULL, ds TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(sid,ds));
"""


@contextmanager
def transaction():
    db = sqlite3.connect(os.environ.get("SENTINELOPS_DB", "sentinelops.db"), timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_dataset(sid, data, db=None):
    payload = {k: v for k, v in data.items() if k != "clean"}
    payload["clean_json"] = data["clean"].to_json(orient="split", date_format="iso", double_precision=15)
    raw = json.dumps(payload, allow_nan=False)
    if db is not None:
        db.execute("INSERT OR REPLACE INTO datasets VALUES(?,?)", (sid, raw))
    else:
        with transaction() as con:
            con.execute("INSERT OR REPLACE INTO datasets VALUES(?,?)", (sid, raw))


def load_dataset(sid):
    db = sqlite3.connect(os.environ.get("SENTINELOPS_DB", "sentinelops.db"), timeout=30)
    db.row_factory = sqlite3.Row
    try:
        row = db.execute("SELECT payload FROM datasets WHERE sid=?", (sid,)).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc): raise
        return None
    finally:
        db.close()
    if not row:
        return None
    data = json.loads(row["payload"])
    # Do not coerce equipment identifiers such as 001 into integers on reload.
    raw = data.pop("clean_json")
    table = json.loads(raw)
    data["clean"] = pd.DataFrame(table["data"], columns=table["columns"])
    data["clean"][data["map"]["timestamp"]] = pd.to_datetime(data["clean"][data["map"]["timestamp"]], utc=True)
    data["clean"][data["map"]["id"]] = data["clean"][data["map"]["id"]].astype(str)
    return data


def empty_workspace():
    return {"context": {k: [] for k in ("assets", "parts", "orders", "windows", "failures", "documents", "dependencies", "changes")}, "cases": {}, "reservations": {}, "approvals": {}, "audit": []}


def save_model(sid, dataset_id, model):
    with transaction() as db:
        row = db.execute("SELECT payload FROM datasets WHERE sid=?", (sid,)).fetchone()
        if not row: raise ValueError("Dataset changed while training. Train again on the active dataset.")
        value = json.loads(row["payload"])
        if value["id"] != dataset_id: raise ValueError("Dataset changed while training. Train again on the active dataset.")
        value["model"] = model
        db.execute("UPDATE datasets SET payload=? WHERE sid=?", (json.dumps(value, allow_nan=False), sid))


def load_workspace(db, sid, ds):
    row = db.execute("SELECT payload FROM workspaces WHERE sid=? AND ds=?", (sid, ds)).fetchone()
    return json.loads(row["payload"]) if row else empty_workspace()


def save_workspace(db, sid, ds, value):
    db.execute("INSERT OR REPLACE INTO workspaces VALUES(?,?,?)", (sid, ds, json.dumps(value, allow_nan=False)))
