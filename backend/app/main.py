import json, os, sqlite3, uuid
import numpy as np
from datetime import date, datetime, timezone
from typing import Literal
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel
from . import analytics as A

app = FastAPI(title="SentinelOps")
SESS: dict = {}  # per-session state: {"pending": ..., "active": ...}. Datasets are isolated by X-Session id.
SCHEMA = """create table if not exists alert_status(sid text, ds text, key text, status text, primary key(sid, ds, key));
create table if not exists work_orders(id integer primary key autoincrement, sid text, ds text, title text, asset text, assignee text default '', due text default '', status text default 'Open');"""
MAX = lambda: int(os.environ.get("SENTINELOPS_MAX_MB", "50")) * 1048576


def q(sql, args=(), many=False):
    c = sqlite3.connect(os.environ.get("SENTINELOPS_DB", "sentinelops.db")); c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA); cur = c.execute(sql, args); c.commit()
        return [dict(r) for r in cur.fetchall()] if many else cur.lastrowid
    finally:
        c.close()


def sid(x_session: str = Header(None)):
    if not x_session or len(x_session) < 8: raise HTTPException(400, "Missing X-Session header.")
    return x_session


def active(s):
    a = SESS.get(s, {}).get("active")
    if not a: raise HTTPException(409, "No active dataset. Upload and process a dataset first.")
    return a


def wipe(s):
    for t in ("alert_status", "work_orders"): q(f"delete from {t} where sid=?", (s,))


class Mapping(BaseModel):
    timestamp: str; id: str; failure: str | None = None; sensors: list[str]
class AlertPatch(BaseModel):
    key: str; status: str
class WOIn(BaseModel):
    title: str; asset: str | None = None
class WOPatch(BaseModel):
    assignee: str | None = None
    due: date | Literal[""] | None = None
    status: Literal["Open", "In progress", "Done"] | None = None


@app.get("/api/state")
def state(s=Depends(sid)):
    a = SESS.get(s, {}).get("active")
    return {"unlocked": bool(a), "dataset": a and {"name": a["name"], "quality": a["quality"], "mapping": a["map"], "machines": len(a["result"]["assets"])}}


@app.post("/api/datasets")
async def upload(file: UploadFile = File(...), s=Depends(sid)):
    raw = await file.read(MAX() + 1)
    if len(raw) > MAX(): raise HTTPException(413, "File is too large.")
    try: df = A.read_upload(file.filename or "", raw)
    except ValueError as e: raise HTTPException(400, str(e))
    SESS.setdefault(s, {})["pending"] = {"df": df, "name": file.filename}  # active dataset is untouched until processing succeeds
    return {"name": file.filename, "rows": len(df), "columns": list(df.columns), "mapping": A.infer(df), "preview": json.loads(df.head(5).to_json(orient="records"))}


def pending(s):
    p = SESS.get(s, {}).get("pending")
    if not p: raise HTTPException(409, "Upload a file first.")
    return p


@app.post("/api/datasets/check")
def check(m: Mapping, s=Depends(sid)):
    p = pending(s); errs = A.blockers(p["df"], m.model_dump())
    if errs: raise HTTPException(422, errs)
    return A.quality(p["df"], m.model_dump())


@app.post("/api/datasets/process")
def process(m: Mapping, s=Depends(sid)):
    p, mp = pending(s), m.model_dump(); errs = A.blockers(p["df"], mp)
    if errs: raise HTTPException(422, errs)
    try: result, d = A.analyse(p["df"], mp)
    except ValueError as e: raise HTTPException(422, str(e))
    if not result["assets"]: raise HTTPException(422, ["No usable rows remain after cleaning."])
    quality = A.quality(p["df"], mp)
    wipe(s)  # invalidate everything derived from the previous dataset
    SESS[s] = {"active": {"id": uuid.uuid4().hex[:12], "name": p["name"], "map": mp, "quality": quality, "result": result, "clean": d, "model": None}}
    return {"quality": SESS[s]["active"]["quality"]}


@app.delete("/api/dataset")
def clear(s=Depends(sid)):
    SESS.pop(s, None); wipe(s); return {"cleared": True}


def slim(a, points=False):
    return {**a, "sensors": {k: {x: y for x, y in v.items() if points or x != "points"} for k, v in a["sensors"].items()}}


@app.get("/api/overview")
def overview(s=Depends(sid)):
    a = active(s); R = a["result"]["assets"]; fl = a["map"].get("failure")
    cnt = {k: sum(x["status"] == k for x in R) for k in ("critical", "watch", "healthy", "unscored")}
    tf = sum(x["failures"] or 0 for x in R)
    wo = q("select status from work_orders where sid=? and ds=?", (s, a["id"]), many=True)
    na = lambda why: {"available": False, "reason": why}
    return {"dataset": a["name"], "kpis": {
        "equipment": {"value": len(R), "definition": "Distinct values in the equipment ID column."},
        "health": {**cnt, "definition": "Critical/Watch when the last 3 readings of any sensor sit 3/1.5 standard deviations from that machine's own baseline (its first 60% of history)."},
        "failures": ({"available": True, "value": tf, "rate_pct": round(100 * tf / a["result"]["records"], 2), "definition": "Rows flagged 1 in the failure column."} if fl else na("No failure column was mapped.")),
        "open_work_orders": {"value": sum(w["status"] != "Done" for w in wo), "definition": "Work orders created in this app. None are imported from the dataset."},
        "remaining_useful_life": na("Needs repeated run-to-failure histories. Not estimated from this file."),
        "cost_exposure": na("No cost or production-impact columns exist.")}}


@app.get("/api/equipment")
def equipment(s=Depends(sid)): return [slim(x) for x in active(s)["result"]["assets"]]


@app.get("/api/equipment/{aid}")
def equipment_one(aid: str, s=Depends(sid)):
    x = next((x for x in active(s)["result"]["assets"] if x["id"] == aid), None)
    if not x: raise HTTPException(404, "Unknown equipment.")
    return slim(x, True)


@app.get("/api/alerts")
def alerts(status: str | None = None, s=Depends(sid)):
    a = active(s); st = {r["key"]: r["status"] for r in q("select key,status from alert_status where sid=? and ds=?", (s, a["id"]), many=True)}
    out = [{**x, "status": st.get(x["key"], "Open")} for x in a["result"]["alerts"]]
    return [x for x in out if not status or x["status"] == status]


@app.patch("/api/alerts/status")
def alert_status(p: AlertPatch, s=Depends(sid)):
    a = active(s)
    if p.status not in ("Open", "Acknowledged", "Resolved"): raise HTTPException(422, "Status must be Open, Acknowledged or Resolved.")
    if p.key not in {x["key"] for x in a["result"]["alerts"]}: raise HTTPException(404, "Unknown alert.")
    q("insert or replace into alert_status values(?,?,?,?)", (s, a["id"], p.key, p.status)); return {"key": p.key, "status": p.status}


@app.get("/api/maintenance/recommendations")
def recs(s=Depends(sid)): return A.recommendations(active(s)["result"]["assets"])


@app.get("/api/workorders")
def wos(s=Depends(sid)): return q("select * from work_orders where sid=? and ds=? order by id", (s, active(s)["id"]), many=True)


@app.post("/api/workorders")
def wo_new(p: WOIn, s=Depends(sid)):
    a = active(s); title = p.title.strip()
    if not title: raise HTTPException(422, "A work order title is required.")
    if p.asset is not None and p.asset not in {x["id"] for x in a["result"]["assets"]}:
        raise HTTPException(422, "Choose equipment from the active dataset.")
    return {"id": q("insert into work_orders(sid,ds,title,asset) values(?,?,?,?)", (s, a["id"], title, p.asset))}


@app.patch("/api/workorders/{wid}")
def wo_patch(wid: int, p: WOPatch, s=Depends(sid)):
    a = active(s)
    if not q("select id from work_orders where id=? and sid=? and ds=?", (wid, s, a["id"]), many=True): raise HTTPException(404, "Unknown work order.")
    fields = p.model_dump(exclude_none=True, mode="json")
    if fields:
        q(f"update work_orders set {', '.join(k+'=?' for k in fields)} where id=? and sid=? and ds=?", (*fields.values(), wid, s, a["id"]))
    return {"id": wid}


@app.get("/api/model")
def model_get(s=Depends(sid)):
    return active(s)["model"] or {"trained": False, "hint": "No model has been trained for this dataset. Use Train model."}


@app.post("/api/model/train")
def model_train(s=Depends(sid)):
    from sklearn.ensemble import IsolationForest, RandomForestClassifier
    from sklearn.metrics import confusion_matrix, precision_score, recall_score, roc_auc_score
    a = active(s); d, m = a["clean"], a["map"]
    X = d[m["sensors"]].copy()
    for c in m["sensors"]:
        name = c + "_avg3"
        while name in X.columns: name += "_avg3"
        X[name] = d.groupby(m["id"])[c].transform(lambda x: x.rolling(3, min_periods=1).mean())
    cut = int(len(d) * .7)  # Learn imputation only from the earlier training rows.
    X = X.fillna(X.iloc[:cut].median()).fillna(0); feats = list(X.columns)
    if not np.isfinite(X.to_numpy()).all() or (X.abs() > np.finfo(np.float32).max).any().any():
        raise HTTPException(422, "Sensor features exceed the numeric range supported by the model. Check units and extreme readings.")
    info = {"trained": True, "version": uuid.uuid4().hex[:8], "trained_at": datetime.now(timezone.utc).isoformat(), "dataset": a["name"], "train_rows": cut, "test_rows": len(d) - cut}
    if m.get("failure"):
        y = d[m["failure"]].to_numpy()
        if y[:cut].sum() < 3 or y[cut:].sum() < 1 or y[:cut].sum() == cut:
            raise HTTPException(422, f"Not enough failure events for time-ordered validation: {int(y[:cut].sum())} in the training period (need 3+), {int(y[cut:].sum())} in the test period (need 1+).")
        mdl = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=0).fit(X[:cut], y[:cut])
        pr = mdl.predict_proba(X[cut:])[:, 1]; pred = (pr >= .5).astype(int)
        tn, fp, fn, tp = confusion_matrix(y[cut:], pred, labels=[0, 1]).ravel()
        metrics = {"roc_auc": float(roc_auc_score(y[cut:], pr)) if len(set(y[cut:])) > 1 else None, "precision": float(precision_score(y[cut:], pred, zero_division=0)),
                   "recall": float(recall_score(y[cut:], pred, zero_division=0)), "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}}
        info.update(task="Failure classification (Random Forest, class-balanced)", metrics=metrics, importances=sorted(zip(feats, map(float, mdl.feature_importances_)), key=lambda t: -t[1])[:8])
    else:
        mdl = IsolationForest(random_state=0).fit(X[:cut]); flagged = float((mdl.predict(X[cut:]) == -1).mean())
        info.update(task="Unsupervised anomaly detection (Isolation Forest)", metrics=None, importances=[],
                    note=f"No failure labels, so accuracy cannot be measured. {100 * flagged:.1f}% of later readings were flagged as unusual.")
    try:
        import mlflow
        with mlflow.start_run(run_name=f"{a['name']}-{info['version']}"):
            mlflow.log_params({"task": info["task"], "train_rows": cut, "test_rows": info["test_rows"]})
            mlflow.log_metrics({k: v for k, v in (info["metrics"] or {}).items() if isinstance(v, float)})
        info["mlflow"] = "logged"
    except Exception as e:  # reported to the user, not hidden
        info["mlflow"] = f"not logged: {type(e).__name__}: {e}"
    info["drift"] = "Drift monitoring is not implemented yet."
    a["model"] = info; return info
