"""Regressions for the independently reproduced QA findings."""
import io
import sqlite3
import uuid

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from app import main as M


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINELOPS_DB", str(tmp_path / "test.db"))
    M.SESS.clear()
    with TestClient(M.app, raise_server_exceptions=False) as c:
        c.headers["X-Session"] = uuid.uuid4().hex
        yield c
    M.SESS.clear()


def telemetry(ids=None, flags=None, values=None):
    values = values if values is not None else [99, 101] * 6 + [100] * 5 + [103] * 3
    return ("timestamp,machine_id,vibration,failure\n" + "\n".join(
        f"2026-01-{i+1:02d},{ids[i] if ids else 'A'},{v},{flags[i] if flags else 0}"
        for i, v in enumerate(values))).encode()


MAP = {"timestamp": "timestamp", "id": "machine_id", "failure": "failure", "sensors": ["vibration"]}


def upload(client, raw=None, name="sample.csv"):
    return client.post("/api/datasets", files={"file": (name, raw if raw is not None else telemetry())})


def activate(client, raw=None, mapping=MAP):
    r = upload(client, raw)
    assert r.status_code == 200, r.text
    r = client.post("/api/datasets/process", json=mapping)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("endpoint", ["check", "process"])
def test_unknown_sensor_is_an_actionable_validation_error(client, endpoint):
    upload(client)
    r = client.post(f"/api/datasets/{endpoint}", json={**MAP, "sensors": ["vibration", "absent"]})
    assert r.status_code == 422, r.text
    assert "absent" in r.text


@pytest.mark.parametrize("header", ["vibration,vibration", "vibration, vibration", "vibration,"])
def test_duplicate_or_blank_headers_are_rejected(client, header):
    raw = ("timestamp,machine_id," + header + "\n2026-01-01,A,1,2").encode()
    r = upload(client, raw)
    assert r.status_code == 400, r.text


@pytest.mark.parametrize("excel", [False, True])
def test_upload_preserves_distinct_text_equipment_ids(client, excel):
    raw = telemetry(ids=["001"] * 10 + ["1"] * 10)
    name = "sample.csv"
    if excel:
        frame = pd.read_csv(io.BytesIO(raw), dtype=str)
        b = io.BytesIO()
        frame.to_excel(b, index=False)
        raw, name = b.getvalue(), "sample.xlsx"
    assert upload(client, raw, name).status_code == 200
    assert client.post("/api/datasets/process", json=MAP).status_code == 200
    equipment = client.get("/api/equipment").json()
    assert {a["id"] for a in equipment} == {"001", "1"}
    assert all(a["records"] == 10 for a in equipment)


def test_na_is_a_valid_literal_equipment_id(client):
    activate(client, telemetry(ids=["NA"] * 20))
    assert client.get("/api/equipment").json()[0]["id"] == "NA"


def test_equivalent_numeric_rows_are_deduplicated_without_changing_ids(client):
    raw = telemetry(ids=["001"] * 20, flags=["1"] * 20, values=[100] * 20)
    raw += b"\n2026-01-01,001,100.0,1.0"
    upload(client, raw)
    quality = client.post("/api/datasets/check", json=MAP).json()
    assert quality["duplicates"] == 1
    assert client.post("/api/datasets/process", json=MAP).status_code == 200
    equipment = client.get("/api/equipment").json()[0]
    assert equipment["id"] == "001" and equipment["records"] == 20 and equipment["failures"] == 20


def test_numeric_equipment_ids_are_not_inferred_as_timestamps(client):
    raw = ("machine_id,recorded_at,temperature\n" + "\n".join(
        f"2024,2026-01-{i+1:02d},60" for i in range(20))).encode()
    mapping = upload(client, raw).json()["mapping"]
    assert mapping["timestamp"] == "recorded_at"
    assert mapping["id"] == "machine_id"


@pytest.mark.parametrize("flag", ["yes", "2", ""])
@pytest.mark.parametrize("endpoint", ["check", "process"])
def test_unknown_or_missing_failure_flags_cannot_be_counted_as_negative(client, flag, endpoint):
    upload(client, telemetry(flags=[flag] * 20))
    r = client.post(f"/api/datasets/{endpoint}", json=MAP)
    assert r.status_code == 422, r.text


def test_supported_boolean_flags_allow_surrounding_whitespace(client):
    activate(client, telemetry(flags=[" true "] + [" false "] * 19))
    failures = client.get("/api/overview").json()["kpis"]["failures"]
    assert failures["value"] == 1 and failures["rate_pct"] == 5.0


@pytest.mark.parametrize("value", ["inf", "-inf", "1e308"])
def test_nonfinite_or_overflowing_analysis_returns_validation_error(client, value):
    upload(client, telemetry(values=[value] * 20))
    r = client.post("/api/datasets/process", json=MAP)
    assert r.status_code == 422, r.text
    assert client.get("/api/state").json()["unlocked"] is False


def test_exponent_overflow_cannot_silently_become_a_missing_sensor(client):
    upload(client, telemetry(values=[99, 101] * 9 + [100, "1e309"]))
    assert client.post("/api/datasets/check", json=MAP).status_code == 422


@pytest.mark.parametrize("token", ["NA", "NaN", "bad-number"])
def test_quality_reports_sensor_values_that_analysis_will_skip(client, token):
    upload(client, telemetry(values=[99, 101] * 9 + [100, token]))
    quality = client.post("/api/datasets/check", json=MAP).json()
    assert quality["missing"] == 1 and quality["missing_pct"] == 1.25


def test_delimiter_bearing_alert_pairs_have_independent_status(client):
    rows = ["timestamp,machine_id,C,B|C"]
    for i in range(20):
        for aid in ("A|B", "A"):
            value = 104 if i >= 17 else (99 if i % 2 == 0 else 101)
            rows.append(f"2026-01-{i+1:02d},{aid},{value},{value}")
    activate(client, "\n".join(rows).encode(), {**MAP, "failure": None, "sensors": ["C", "B|C"]})
    alerts = client.get("/api/alerts").json()
    assert len({a["key"] for a in alerts}) == 4
    target = next(a for a in alerts if (a["asset"], a["sensor"]) == ("A", "B|C"))
    assert client.patch("/api/alerts/status", json={"key": target["key"], "status": "Resolved"}).status_code == 200
    after = client.get("/api/alerts").json()
    assert sum(a["status"] == "Resolved" for a in after) == 1


@pytest.mark.parametrize("payload", [{"title": " "}, {"title": "Inspect", "asset": "unknown"}])
def test_invalid_work_order_creation_is_rejected(client, payload):
    activate(client)
    assert client.post("/api/workorders", json=payload).status_code == 422
    assert client.get("/api/workorders").json() == []


@pytest.mark.parametrize("patch", [{"status": ""}, {"due": "not-a-date"}, {"due": "2026-02-30"}])
def test_invalid_work_order_update_does_not_change_record(client, patch):
    activate(client)
    wid = client.post("/api/workorders", json={"title": "Inspect A", "asset": "A"}).json()["id"]
    assert client.patch(f"/api/workorders/{wid}", json=patch).status_code == 422
    record = client.get("/api/workorders").json()[0]
    assert record["status"] == "Open" and record["due"] == ""


def test_work_order_update_rolls_back_all_fields_on_database_failure(client):
    activate(client)
    wid = client.post("/api/workorders", json={"title": "Inspect A"}).json()["id"]
    import os
    with sqlite3.connect(os.environ["SENTINELOPS_DB"]) as db:
        db.execute("CREATE TRIGGER reject_done BEFORE UPDATE OF status ON work_orders WHEN NEW.status='Done' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    assert client.patch(f"/api/workorders/{wid}", json={"assignee": "Changed", "status": "Done"}).status_code == 500
    assert client.get("/api/workorders").json()[0]["assignee"] == ""


@pytest.mark.parametrize("n", [201, 399, 400, 401])
def test_chart_sampling_is_bounded_and_keeps_latest_evidence(client, n):
    rows = [f"{(pd.Timestamp('2026-01-01')+pd.Timedelta(hours=i)).isoformat()},A,{i}" for i in range(n)]
    raw = ("timestamp,machine_id,vibration\n" + "\n".join(rows)).encode()
    activate(client, raw, {**MAP, "failure": None})
    points = client.get("/api/equipment/A").json()["sensors"]["vibration"]["points"]
    assert len(points) <= 200
    assert points[0]["v"] == 0 and points[-1]["v"] == n - 1


def test_alert_timestamp_reflects_last_valid_sensor_reading(client):
    rows = []
    for i in range(20):
        v = "" if i >= 17 else 104 if i >= 14 else 99 if i % 2 == 0 else 101
        rows.append(f"2026-01-{i+1:02d},A,{v}")
    activate(client, ("timestamp,machine_id,vibration\n"+"\n".join(rows)).encode(), {**MAP, "failure": None})
    assert client.get("/api/alerts").json()[0]["data_timestamp"] == "2026-01-17 00:00"


def test_invalid_replacement_preserves_current_orders_and_dataset(client):
    activate(client)
    client.post("/api/workorders", json={"title": "Keep me"})
    upload(client, telemetry(values=["inf"] * 20))
    assert client.post("/api/datasets/process", json=MAP).status_code == 422
    assert client.get("/api/overview").status_code == 200
    assert client.get("/api/workorders").json()[0]["title"] == "Keep me"


def capture_model_inputs(monkeypatch):
    seen = []
    class Forest:
        def __init__(self, **kwargs): pass
        def fit(self, x): seen.append(x.copy()); return self
        def predict(self, x): return np.ones(len(x), dtype=int)
    monkeypatch.setattr("sklearn.ensemble.IsolationForest", Forest)
    return seen


def test_future_values_cannot_change_training_imputation(client, monkeypatch):
    seen = capture_model_inputs(monkeypatch)
    for future in (100, -100):
        values = list(range(1, 15)) + [future] * 6
        values[1] = ""
        activate(client, telemetry(values=values), {**MAP, "failure": None})
        assert client.post("/api/model/train").status_code == 200
    # Training has values 1,3,...,14, so its median is 8 regardless of the future.
    assert seen[0].iloc[1, 0] == 8.0
    pd.testing.assert_frame_equal(seen[0], seen[1])


def test_generated_features_cannot_overwrite_an_uploaded_sensor(client, monkeypatch):
    seen = capture_model_inputs(monkeypatch)
    rows = [f"2026-01-{i+1:02d},A,{i+1},1000" for i in range(20)]
    activate(client, ("timestamp,machine_id,x,x_avg3\n"+"\n".join(rows)).encode(), {**MAP, "failure": None, "sensors": ["x", "x_avg3"]})
    assert client.post("/api/model/train").status_code == 200
    x = seen[0]
    assert x.columns.is_unique and x.shape[1] == 4
    assert (x["x_avg3"] == 1000).all()


def test_training_reports_values_outside_estimator_numeric_range(client):
    activate(client, telemetry(values=[1e40]+list(range(101,120))), {**MAP, "failure": None})
    assert client.post("/api/model/train").status_code == 422
    assert client.get("/api/model").json()["trained"] is False
