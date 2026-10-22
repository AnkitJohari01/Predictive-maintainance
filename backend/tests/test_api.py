import os, tempfile, uuid
os.environ["SENTINELOPS_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
H = lambda s: {"X-Session": s}
new = lambda: uuid.uuid4().hex


def make_csv(fails=None, dup=True, miss=True):
    fails = fails if fails is not None else {"B": [5]}
    rows = ["timestamp,machine_id,vibration,temperature,failure"]
    for d in range(30):
        for m in "ABC":
            v = 2 + 0.01 * ((d * 7) % 5) + ((d - 21) * 0.8 if m == "A" and d >= 22 else 0)
            t = "" if (miss and m == "C" and d == 10) else f"{60 + 0.1 * ((d * 3) % 4):.1f}"
            rows.append(f"2026-09-{d + 1:02d},{m},{v:.2f},{t},{int(d in fails.get(m, []))}")
    if dup: rows.append(rows[5])
    return "\n".join(rows)


def up(s, csv, name="d.csv"): return c.post("/api/datasets", files={"file": (name, csv.encode())}, headers=H(s))
def ready(s, csv=None):
    r = up(s, csv or make_csv()); assert r.status_code == 200, r.text
    p = c.post("/api/datasets/process", json=r.json()["mapping"], headers=H(s)); assert p.status_code == 200, p.text
    return r.json()


def test_locked_before_upload():
    s = new()
    assert c.get("/api/state", headers=H(s)).json()["unlocked"] is False
    for p in ("/api/overview", "/api/alerts", "/api/equipment", "/api/workorders"): assert c.get(p, headers=H(s)).status_code == 409
def test_requires_session_header(): assert c.get("/api/state").status_code == 400
def test_schema_inference():
    m = up(new(), make_csv()).json()["mapping"]
    assert (m["timestamp"], m["id"], m["failure"]) == ("timestamp", "machine_id", "failure") and m["sensors"] == ["vibration", "temperature"]
def test_rejects_unsupported_type():
    r = up(new(), "a,b,c", "x.txt"); assert r.status_code == 400 and "not supported" in r.json()["detail"]
def test_blocks_too_few_rows():
    s = new(); r = up(s, "timestamp,machine_id,v\n" + "\n".join(f"2026-01-0{i},A,{i}" for i in range(1, 6)))
    p = c.post("/api/datasets/process", json=r.json()["mapping"], headers=H(s)); assert p.status_code == 422 and "20" in p.json()["detail"][0]
def test_missing_mapping_blocked():
    s = new(); up(s, make_csv()); p = c.post("/api/datasets/check", json={"timestamp": "nope", "id": "machine_id", "sensors": ["vibration"]}, headers=H(s)); assert p.status_code == 422
def test_quality_counts():
    s = new(); r = up(s, make_csv()); q = c.post("/api/datasets/check", json=r.json()["mapping"], headers=H(s)).json()
    assert q["duplicates"] == 1 and q["missing"] == 1 and q["rows"] == 91
def test_overview_kpis_from_data():
    s = new(); ready(s); k = c.get("/api/overview", headers=H(s)).json()["kpis"]
    assert k["equipment"]["value"] == 3 and k["health"]["critical"] == 1 and k["health"]["healthy"] == 2
    assert k["failures"]["value"] == 1 and k["remaining_useful_life"]["available"] is False
def test_no_failure_column_marks_unavailable():
    s = new(); csv = "\n".join(",".join(l.split(",")[:4]) for l in make_csv().split("\n")); ready(s, csv)
    assert c.get("/api/overview", headers=H(s)).json()["kpis"]["failures"]["available"] is False
def test_alert_generated_and_status_persists():
    s = new(); ready(s); al = c.get("/api/alerts", headers=H(s)).json()
    a = al[0]; assert a["asset"] == "A" and a["sensor"] == "vibration" and a["severity"] == "critical" and a["status"] == "Open"
    assert c.patch("/api/alerts/status", json={"key": a["key"], "status": "Acknowledged"}, headers=H(s)).status_code == 200
    assert c.get("/api/alerts?status=Acknowledged", headers=H(s)).json()[0]["key"] == a["key"]
    assert c.patch("/api/alerts/status", json={"key": "zzz", "status": "Resolved"}, headers=H(s)).status_code == 404
def test_work_order_lifecycle():
    s = new(); ready(s); w = c.post("/api/workorders", json={"title": "Inspect A", "asset": "A"}, headers=H(s)).json()["id"]
    c.patch(f"/api/workorders/{w}", json={"assignee": "R. Sharma", "due": "2026-10-30", "status": "In progress"}, headers=H(s))
    row = c.get("/api/workorders", headers=H(s)).json()[0]; assert (row["assignee"], row["status"]) == ("R. Sharma", "In progress")
    assert c.patch(f"/api/workorders/{w}", json={"status": "bogus"}, headers=H(s)).status_code == 422
def test_replace_dataset_clears_derived_results():
    s = new(); ready(s); a = c.get("/api/alerts", headers=H(s)).json()[0]
    c.patch("/api/alerts/status", json={"key": a["key"], "status": "Resolved"}, headers=H(s)); c.post("/api/workorders", json={"title": "x"}, headers=H(s))
    ready(s)
    assert c.get("/api/workorders", headers=H(s)).json() == [] and c.get("/api/alerts", headers=H(s)).json()[0]["status"] == "Open"
def test_failed_upload_keeps_active_dataset():
    s = new(); ready(s); assert up(s, "junk", "bad.txt").status_code == 400
    assert c.get("/api/overview", headers=H(s)).status_code == 200
def test_session_isolation():
    a, b = new(), new(); ready(a); assert c.get("/api/overview", headers=H(b)).status_code == 409
def test_clear_relocks():
    s = new(); ready(s); c.delete("/api/dataset", headers=H(s)); assert c.get("/api/overview", headers=H(s)).status_code == 409
def test_model_untrained_then_insufficient_failures():
    s = new(); ready(s); assert c.get("/api/model", headers=H(s)).json()["trained"] is False
    r = c.post("/api/model/train", headers=H(s)); assert r.status_code == 422 and "failure events" in r.json()["detail"]
def test_model_trains_with_time_split():
    s = new(); ready(s, make_csv({"C": [3, 5, 8, 25, 27]})); r = c.post("/api/model/train", headers=H(s)).json()
    assert r["trained"] and set(r["metrics"]) >= {"roc_auc", "precision", "recall", "confusion_matrix"} and "mlflow" in r
