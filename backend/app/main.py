import json, os, sqlite3, uuid
import pandas as pd
from datetime import date, datetime, timezone
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from . import analytics as A
from . import storage as S

app = FastAPI(title="SentinelOps")
SESS: dict = {}  # Unprocessed pending uploads only. Active datasets and workflows persist in SQLite.
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
    a = S.load_dataset(s)
    if not a: raise HTTPException(409, "No active dataset. Upload and process a dataset first.")
    return a


def wipe(s):
    for t in ("alert_status", "work_orders"): q(f"delete from {t} where sid=?", (s,))
    with S.transaction() as db:
        db.execute("DELETE FROM workspaces WHERE sid=?", (s,))


class Mapping(BaseModel):
    timestamp: str | None = None; id: str | None = None; failure: str | None = None; sensors: list[str]
class AlertPatch(BaseModel):
    key: str; status: str
class WOIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    asset: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        if not value.strip(): raise ValueError("Work order title cannot be empty.")
        return value.strip()
class WOPatch(BaseModel):
    assignee: str | None = None; due: str | None = None; status: str | None = None


@app.post("/api/bundles")
async def bundle_upload(file: UploadFile = File(...), s=Depends(sid)):
    from .workspace import Context, validate_context, event
    from pydantic import ValidationError
    SESS.setdefault(s, {}).pop("pending", None)
    raw = await file.read(MAX()+1)
    if len(raw) > MAX(): raise HTTPException(413, "Bundle is too large.")
    if not (file.filename or "").lower().endswith(".json"): raise HTTPException(422, "A complete bundle must be JSON.")
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get("telemetry"), list) or not value["telemetry"] or any(not isinstance(r, dict) for r in value["telemetry"]):
            raise ValueError("Bundle requires a non-empty telemetry array of records.")
        if set(value)-set(Context.model_fields)-{"telemetry", "sensors", "mapping"}: raise ValueError("Bundle contains unrecognized sections.")
        df = pd.DataFrame(value["telemetry"])
        mp = value.get("mapping") or A.infer(df)
        if "sensors" in value: mp["sensors"] = value["sensors"]
        mp = Mapping.model_validate(mp).model_dump()
        errs = A.blockers(df, mp)
        if errs: raise HTTPException(422, errs)
        result, clean = A.analyse(df, mp)
        dataset = {"id": uuid.uuid4().hex[:12], "name": file.filename, "map": mp, "quality": A.quality(df, mp), "result": result, "clean": clean, "model": None}
        ctx = validate_context(Context.model_validate({k: value[k] for k in Context.model_fields if k in value}).model_dump(), dataset)
        workspace = S.empty_workspace(); workspace["context"] = ctx
        event(workspace, "Complete bundle processed", file.filename)
    except (ValueError, TypeError, KeyError, ValidationError, OverflowError) as exc:
        raise HTTPException(422, "Bundle validation failed: "+str(exc)[:1500])
    q("select 1")
    with S.transaction() as db:
        for table in ("alert_status", "work_orders", "workspaces"):
            db.execute(f"DELETE FROM {table} WHERE sid=?", (s,))
        S.save_dataset(s, dataset, db)
        S.save_workspace(db, s, dataset["id"], workspace)
    SESS.pop(s, None)
    return {"processed": True, "quality": dataset["quality"]}


@app.get("/api/state")
def state(s=Depends(sid)):
    a = S.load_dataset(s)
    return {"unlocked": bool(a), "dataset": a and {"name": a["name"], "quality": a["quality"], "mapping": a["map"], "machines": len(a["result"]["assets"])}}


@app.post("/api/datasets")
async def upload(file: UploadFile = File(...), s=Depends(sid)):
    SESS.setdefault(s, {}).pop("pending", None)
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
    try:
        result, d = A.analyse(p["df"], mp)
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(422, "The selected data could not be processed. Check timestamps, equipment IDs and sensor values.") from exc
    if not result["assets"]: raise HTTPException(422, ["No usable rows remain after cleaning."])
    dataset = {"id": uuid.uuid4().hex[:12], "name": p["name"], "map": mp, "quality": A.quality(p["df"], mp), "result": result, "clean": d, "model": None}
    # Swap data and dependent state atomically after validation succeeds.
    q("select 1")
    with S.transaction() as db:
        for table in ("alert_status", "work_orders", "workspaces"):
            db.execute(f"DELETE FROM {table} WHERE sid=?", (s,))
        S.save_dataset(s, dataset, db)
    SESS.pop(s, None)
    return {"quality": dataset["quality"]}


@app.delete("/api/dataset")
def clear(s=Depends(sid)):
    SESS.pop(s, None)
    q("select 1")
    with S.transaction() as db:
        for table in ("alert_status", "work_orders", "workspaces", "datasets"):
            db.execute(f"DELETE FROM {table} WHERE sid=?", (s,))
    return {"cleared": True}


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
        "cost_exposure": na("Cost and production impact inputs have no configured mapping.")}}


@app.get("/api/equipment")
def equipment(s=Depends(sid)): return [slim(x) for x in active(s)["result"]["assets"]]


@app.get("/api/equipment/{aid:path}")
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
    with S.transaction() as db:
        w = S.load_workspace(db, s, a["id"])
        aid = next(x["asset"] for x in a["result"]["alerts"] if x["key"] == p.key)
        if p.status == "Resolved" and w["context"]["assets"] and not w["cases"].get(aid, {}).get("closed"):
            raise HTTPException(409, "Resolve through the case workspace after recording disposition, findings and verification evidence.")
        record=w["cases"].get(aid)
        if p.status != "Resolved" and record and record["closed"]:
            record.update(closed=False,approved=False,scope_reviewed=False,production_reviewed=False,permit_reviewed=False,verification_value=None,verification_note="",verification_at="")
            w["approvals"].pop(aid,None)
            for alert in a["result"]["alerts"]:
                if alert["asset"] == aid: db.execute("INSERT OR REPLACE INTO alert_status VALUES(?,?,?,?)",(s,a["id"],alert["key"],"Open"))
            if record.get('work_order_id'): db.execute("UPDATE work_orders SET status='Open' WHERE id=? AND sid=? AND ds=?",(record['work_order_id'],s,a['id']))
            from .workspace import event
            event(w,"Case reopened via alert",aid)
            S.save_workspace(db,s,a['id'],w)
        db.execute("INSERT OR REPLACE INTO alert_status VALUES(?,?,?,?)",(s,a['id'],p.key,p.status))
    return {"key":p.key,"status":p.status}


@app.get("/api/maintenance/recommendations")
def recs(s=Depends(sid)): return A.recommendations(active(s)["result"]["assets"])


@app.get("/api/workorders")
def wos(s=Depends(sid)): return q("select * from work_orders where sid=? and ds=? order by id", (s, active(s)["id"]), many=True)


@app.post("/api/workorders")
def wo_new(p: WOIn, s=Depends(sid)):
    a = active(s)
    if p.asset is not None and p.asset not in {x["id"] for x in a["result"]["assets"]}:
        raise HTTPException(422, "Choose equipment from the active dataset.")
    return {"id": q("insert into work_orders(sid,ds,title,asset) values(?,?,?,?)", (s, a["id"], p.title, p.asset))}


@app.patch("/api/workorders/{wid}")
def wo_patch(wid: int, p: WOPatch, s=Depends(sid)):
    a = active(s)
    if p.status is not None and p.status not in ("Open", "In progress", "Done"): raise HTTPException(422, "Invalid status.")
    if p.due:
        try: date.fromisoformat(p.due)
        except ValueError: raise HTTPException(422, "Due date must be a valid date in YYYY-MM-DD format.")
    with S.transaction() as db:
        if not db.execute("SELECT id FROM work_orders WHERE id=? AND sid=? AND ds=?",(wid,s,a['id'])).fetchone(): raise HTTPException(404,"Unknown work order.")
        w=S.load_workspace(db,s,a['id'])
        linked=next((r for r in w['cases'].values() if r.get('work_order_id') == wid),None)
        if linked and p.status == 'Done' and not linked['closed']:
            raise HTTPException(409,"Verify and close the linked case before completing this work order.")
        if linked and any(k in p.model_fields_set for k in ('assignee','due')):
            raise HTTPException(409,"Edit ownership and planning through the linked case, then approve the proposal again.")
        if linked and p.status and p.status != 'Done' and linked['closed']:
            raise HTTPException(409,"Reopen the linked case before changing the completed work order.")
        for k,v in p.model_dump(exclude_none=True).items(): db.execute(f"UPDATE work_orders SET {k}=? WHERE id=? AND sid=? AND ds=?",(v,wid,s,a['id']))
    return {"id": wid}


@app.get("/api/model")
def model_get(s=Depends(sid)):
    return active(s)["model"] or {"trained": False, "hint": "No model has been trained for this dataset. Use Train model."}


@app.post("/api/model/train")
def model_train(s=Depends(sid)):
    a = active(s)
    from sklearn.ensemble import IsolationForest, RandomForestClassifier
    from sklearn.metrics import confusion_matrix, precision_score, recall_score, roc_auc_score
    d, m = a["clean"].copy(), a["map"]
    # Keep a whole timestamp on one side of the split; fit imputation on training rows only.
    times = d[m["timestamp"]].drop_duplicates().tolist()
    if len(times) < 2: raise HTTPException(422, "Training needs at least two distinct timestamps for time-ordered validation.")
    boundary = times[max(1, int(len(times) * .7))]
    cut = int((d[m["timestamp"]] < boundary).sum())
    X = d[m["sensors"]].copy()
    feats = list(m["sensors"])
    for i, col in enumerate(m["sensors"]):
        feature = f"Rolling mean 3: {col}"
        while feature in X.columns: feature = "Derived " + feature
        X[feature] = d.groupby(m["id"])[col].transform(lambda x: x.rolling(3, min_periods=1).mean())
        feats.append(feature)
    if X.iloc[:cut].notna().sum().sum() == 0:
        raise HTTPException(422, "No usable sensor readings in the training period.")
    X = X.fillna(X.iloc[:cut].median()).fillna(0)
    info = {"trained": True, "version": uuid.uuid4().hex[:8], "trained_at": datetime.now(timezone.utc).isoformat(), "dataset": a["name"], "train_rows": cut, "test_rows": len(d) - cut,
            "validation": "Earlier timestamps train; later timestamps test. Missing values use training-period medians. Metrics classify observed failure flags, not future failure dates."}
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
    try: S.save_model(s, a["id"], info)
    except ValueError as exc: raise HTTPException(409, str(exc))
    return info


from .workspace import install
install(app, active, sid, q)
