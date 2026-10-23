"""Validated maintenance context, decision records and deterministic planning."""
import json
import math
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from . import storage as S
from . import analytics as A


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Asset(Record):
    asset_id: str = Field(min_length=1, max_length=200)
    name: str = ""
    site: str = ""
    line: str = ""
    asset_class: str = ""
    criticality: str = "Unknown"
    owner: str = ""
    part_id: str = ""
    part_qty: int = Field(default=1, ge=1)
    repair_hours: float | None = Field(default=None, gt=0, le=720)
    skill: str = ""
    downtime_cost_per_hour: float | None = Field(default=None, ge=0)
    operating_hours: float | None = Field(default=None, ge=0)
    observation_start: str = ""
    observation_end: str = ""


class Part(Record):
    part_id: str = Field(min_length=1)
    description: str = ""
    on_hand: int = Field(ge=0)
    reserved: int = Field(default=0, ge=0)
    min_stock: int | None = Field(default=None, ge=0)
    lead_days: float = Field(ge=0)
    unit_cost: float | None = Field(default=None, ge=0)
    supplier: str = ""


class Window(Record):
    window_id: str = Field(min_length=1)
    asset_id: str
    start: str
    end: str
    crew_skill: str
    crew_count: int = Field(ge=0)
    required_crew: int = Field(ge=1)
    resource_pool_id: str = ""
    production_state: str = ""


class Failure(Record):
    event_id: str = Field(min_length=1)
    asset_id: str
    failed_at: str
    restored_at: str
    failure_mode: str = ""
    corrective_action: str = ""


class Order(Record):
    work_order_id: str = Field(min_length=1)
    asset_id: str
    title: str
    status: str
    assignee: str = ""
    due_at: str = ""
    estimated_hours: float | None = Field(default=None, ge=0)
    labor_cost: float | None = Field(default=None, ge=0)
    material_cost: float | None = Field(default=None, ge=0)
    closed_at: str = ""
    priority: str = ""


class Document(Record):
    document_id: str = Field(min_length=1)
    title: str
    asset_class: str = "All"
    revision: str
    section: str
    text: str = Field(min_length=1, max_length=100000)


class Dependency(Record):
    from_asset: str
    to_asset: str
    service: str
    source: str = ""


class Change(Record):
    change_id: str = Field(min_length=1)
    asset_id: str
    timestamp: str
    description: str


class Context(Record):
    assets: list[Asset] = Field(default_factory=list, max_length=10000)
    parts: list[Part] = Field(default_factory=list, max_length=10000)
    windows: list[Window] = Field(default_factory=list, max_length=10000)
    failures: list[Failure] = Field(default_factory=list, max_length=10000)
    orders: list[Order] = Field(default_factory=list, max_length=10000)
    documents: list[Document] = Field(default_factory=list, max_length=1000)
    dependencies: list[Dependency] = Field(default_factory=list, max_length=10000)
    changes: list[Change] = Field(default_factory=list, max_length=10000)


class CasePatch(Record):
    owner: str | None = Field(default=None, max_length=200)
    due: str | None = None
    disposition: str | None = None
    finding: str | None = Field(default=None, max_length=10000)
    scope_reviewed: bool | None = None
    production_reviewed: bool | None = None
    permit_reviewed: bool | None = None
    verification_sensor: str | None = None
    verification_value: float | None = Field(default=None, ge=0)
    verification_note: str | None = Field(default=None, max_length=10000)
    verification_at: str | None = None


class Scenario(Record):
    asset_id: str
    hours: float = Field(default=4, gt=0, le=720)
    delay_days: float = Field(default=0, ge=0, le=365)
    lead_days: float | None = Field(default=None, ge=0, le=365)
    stock: int | None = Field(default=None, ge=0)
    crew: int | None = Field(default=None, ge=0)
    demand: float | None = Field(default=None, ge=0, le=1e12)
    standby_capacity: float | None = Field(default=None, ge=0, le=1e12)


def dt(value):
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, f"Invalid date/time: {str(value)[:100]}. Use ISO dates or timestamps.")


def event(w, action, detail):
    w["audit"].insert(0, {"at": datetime.now(timezone.utc).isoformat(), "action": action, "detail": detail})


def validate_context(data, dataset):
    ids = {a["id"] for a in dataset["result"]["assets"]}
    for key, idcol in [("assets", "asset_id"), ("parts", "part_id"), ("windows", "window_id"), ("orders", "work_order_id"), ("failures", "event_id"), ("documents", "document_id"), ("changes", "change_id")]:
        values = [r[idcol] for r in data[key]]
        if any(not x.strip() or x != x.strip() for x in values) or len(values) != len(set(values)):
            raise HTTPException(422, f"{key} requires unique, trimmed, non-empty {idcol} values.")
    for key in ("assets", "windows", "orders", "failures", "changes"):
        if any(r["asset_id"] not in ids for r in data[key]):
            raise HTTPException(422, f"{key} contains equipment IDs absent from the active telemetry.")
    partids = {p["part_id"] for p in data["parts"]}
    for a in data["assets"]:
        if a["criticality"] not in ("A", "B", "C", "Unknown"):
            raise HTTPException(422, "Criticality must be A, B, C or Unknown.")
        if a["part_id"] and a["part_id"] not in partids:
            raise HTTPException(422, "Asset part mappings must reference a supplied stock item.")
        if a["operating_hours"] is not None:
            start, end = dt(a["observation_start"]), dt(a["observation_end"])
            if end <= start or a["operating_hours"] > (end-start).total_seconds()/3600:
                raise HTTPException(422, "Operating hours must fit a valid observation period.")
    for p in data["parts"]:
        if p["reserved"] > p["on_hand"]:
            raise HTTPException(422, "Reserved stock cannot exceed on-hand stock.")
    for key, lo, hi in [("windows", "start", "end"), ("failures", "failed_at", "restored_at")]:
        for r in data[key]:
            if dt(r[hi]) <= dt(r[lo]): raise HTTPException(422, f"{key}: end must follow start.")
    for f in data["failures"]:
        for other in data["failures"]:
            if f["event_id"] < other["event_id"] and f["asset_id"] == other["asset_id"] and dt(f["failed_at"]) < dt(other["restored_at"]) and dt(other["failed_at"]) < dt(f["restored_at"]):
                raise HTTPException(422, "Failure intervals for the same equipment cannot overlap.")
    for a in data["assets"]:
        if a["operating_hours"] is None: continue
        start, end = dt(a["observation_start"]), dt(a["observation_end"])
        downtime = sum(max(0, (min(end, dt(f["restored_at"]))-max(start, dt(f["failed_at"]))).total_seconds()/3600) for f in data["failures"] if f["asset_id"] == a["asset_id"])
        if a["operating_hours"]+downtime > (end-start).total_seconds()/3600+1e-8:
            raise HTTPException(422, "Operating hours plus recorded repair downtime exceed the observation period.")
    for dep in data["dependencies"]:
        if dep["from_asset"] not in ids or dep["to_asset"] not in ids or dep["from_asset"] == dep["to_asset"]:
            raise HTTPException(422, "Dependency endpoints must be distinct active equipment IDs.")
    for r in data["changes"]: dt(r["timestamp"])
    for o in data["orders"]:
        if o["status"] not in ("Open", "Planned", "In progress", "Done"): raise HTTPException(422, "Invalid imported work-order status.")
        for field in ("due_at", "closed_at"):
            if o[field]: dt(o[field])
    # Shared windows must agree on pool capacity. Otherwise a second job could raise capacity to evade contention checks.
    windows = data["windows"]
    for i, a in enumerate(windows):
        for b in windows[i+1:]:
            if a["resource_pool_id"] and a["resource_pool_id"] == b["resource_pool_id"] and dt(a["start"]) < dt(b["end"]) and dt(b["start"]) < dt(a["end"]) and (a["crew_count"] != b["crew_count"] or a["crew_skill"] != b["crew_skill"]):
                raise HTTPException(422, "Overlapping windows in a shared pool must agree on capacity and skill.")
    return data


def asset(dataset, w, aid):
    a = next((r for r in dataset["result"]["assets"] if r["id"] == aid), None)
    if a is None: raise HTTPException(404, "Unknown equipment in the active dataset.")
    meta = next((r for r in w["context"]["assets"] if r["asset_id"] == aid), {})
    return {**a, **meta}


def case(w, aid):
    return w["cases"].setdefault(aid, {"owner": "", "due": "", "disposition": "", "finding": "", "scope_reviewed": False, "production_reviewed": False, "permit_reviewed": False, "verification_sensor": "", "verification_value": None, "verification_note": "", "verification_at": "", "closed": False, "approved": False})


def materials(w, a):
    p = next((p for p in w["context"]["parts"] if p["part_id"] == a.get("part_id")), None)
    held = w["reservations"].get(a["id"], {}).get("qty", 0)
    if p is None: return {"part": None, "available": None, "required": a.get("part_qty"), "held": held, "ready": False, "reason": "BOM or inventory missing"}
    allocated = sum(r["qty"] for r in w["reservations"].values() if r["part_id"] == p["part_id"])
    free = p["on_hand"] - p["reserved"] - allocated
    need = a.get("part_qty", 1)
    return {"part": p, "available": free, "required": need, "held": held, "ready": free+held >= need, "reason": "Covered" if free+held >= need else "Parts shortage"}


def assessment(dataset, w, aid, scenario=None):
    a = asset(dataset, w, aid); c = case(w, aid); m = materials(w, a)
    reasons = []
    if not c["owner"].strip(): reasons.append("Assign an accountable owner")
    if not c["disposition"] or not c["finding"].strip(): reasons.append("Record inspection findings and disposition")
    duration = scenario.hours if scenario else a.get("repair_hours")
    if not duration: reasons.append("Confirmed duration missing")
    if not a.get("skill"): reasons.append("Required skill missing")
    now = dt(a["last"].replace(" UTC", "+00:00"))
    # Latest telemetry date is the reproducible analysis date, not the wall clock.
    earliest = now + timedelta(days=scenario.delay_days if scenario else 0)
    stock_ok = scenario.stock >= m["required"] if scenario and scenario.stock is not None and m["required"] else m["ready"]
    if not stock_ok:
        if scenario and scenario.lead_days is not None: earliest = max(earliest, now+timedelta(days=scenario.lead_days))
        else: reasons.append(m["reason"])
    candidates = []
    for win in sorted(w["context"]["windows"], key=lambda r: dt(r["start"])):
        if win["asset_id"] != aid or not duration: continue
        capacity = scenario.crew if scenario and scenario.crew is not None else win["crew_count"]
        occupied = [v for other, v in w["approvals"].items() if other != aid and v["pool"] == win["resource_pool_id"]]
        first = max(dt(win["start"]), earliest)
        starts = sorted({first, *(dt(v["end"]) for v in occupied if dt(v["end"]) >= first and dt(v["end"]) < dt(win["end"]))})
        start, end, booked, fits = first, first+timedelta(hours=duration), 0, False
        for possible in starts:
            finish = possible+timedelta(hours=duration)
            # Check peak simultaneous load, rather than summing sequential bookings across the whole job.
            points = [possible, *(dt(v["start"]) for v in occupied if possible <= dt(v["start"]) < finish)]
            load = max((sum(v["crew"] for v in occupied if dt(v["start"]) <= point < dt(v["end"])) for point in points), default=0)
            if finish <= dt(win["end"]) and win["crew_skill"] == a.get("skill") and load+win["required_crew"] <= capacity:
                start, end, booked, fits = possible, finish, load, True
                break
        candidates.append({**win, "proposed_start": start.isoformat(), "proposed_end": end.isoformat(), "fits": fits, "booked_crew": booked})
    chosen = next((r for r in candidates if r["fits"]), None)
    if not chosen: reasons.append("No window fits duration, skill and shared crew capacity")
    elif not chosen["resource_pool_id"]: reasons.append("Shared crew pool not identified")
    return {"asset_id": aid, "materials": m, "candidate": chosen, "windows": candidates, "blockers": reasons, "stage": "Verified" if c["closed"] else "Approved proposal" if c["approved"] else "Needs inspection" if not c["disposition"] else "Blocked" if reasons else "Ready for approval"}


def reliability(w):
    ctx = w["context"]; events = ctx["failures"]
    hours = lambda f: (dt(f["restored_at"])-dt(f["failed_at"])).total_seconds()/3600
    exposed = [a for a in ctx["assets"] if a["operating_hours"] is not None]
    matched = [f for f in events for a in exposed if a["asset_id"] == f["asset_id"] and dt(f["failed_at"]) >= dt(a["observation_start"]) and dt(f["restored_at"]) <= dt(a["observation_end"])]
    run = sum(a["operating_hours"] for a in exposed)
    unmatched = len(events)-len(matched)
    valid = bool(run and matched and not unmatched)
    repaired = sum(hours(f) for f in matched)
    costed = [o for o in ctx["orders"] if o["status"] == "Done" and o["labor_cost"] is not None and o["material_cost"] is not None]
    return {"failure_events": len(events), "mttr_hours": sum(hours(f) for f in events)/len(events) if events else None, "mtbf_hours": run/len(matched) if valid else None, "recorded_availability_pct": 100*run/(run+repaired) if valid else None, "operating_hours": run if exposed else None, "unmatched_events": unmatched, "actual_spend": sum(o["labor_cost"]+o["material_cost"] for o in costed) if costed else None, "costed_orders": len(costed), "verified_savings": None, "definition": "MTBF = supplied operating hours / failures matched to exposure periods. Recorded availability = operating / (operating + matched repair hours). Not a schedule-based availability or causal benefit measure."}


def snapshot(dataset, w):
    assets = [{k: v for k, v in asset(dataset, w, a["id"]).items() if k != "sensors"} for a in dataset["result"]["assets"]]
    for a in assets:
        a["readiness"] = assessment(dataset, w, a["id"])
        a["priority"] = a["max_z"] * {"A": 3, "B": 2, "C": 1}.get(a.get("criticality"), 1)
    ctx = w["context"]
    return {**w, "assets": sorted(assets, key=lambda a: -a["priority"]), "reliability": reliability(w), "capabilities": {"condition": True, "planning": bool(ctx["assets"] and ctx["windows"] and ctx["parts"]), "parts": bool(ctx["parts"]), "knowledge": bool(ctx["documents"]), "outcomes": bool(ctx["failures"]), "dependencies": bool(ctx["dependencies"])}, "dataset": dataset["name"], "as_of": max(a["last"] for a in assets)}


def install(app, active, sid, q):
    router = APIRouter(prefix="/api")

    def current(db, s):
        a = active(s)
        return a, S.load_workspace(db, s, a["id"])

    def persist(db, s, a, w):
        S.save_workspace(db, s, a["id"], w)

    def invalidate(db, s, a, w, aid, clear_verification=False):
        c = case(w, aid); c["approved"] = False; c["closed"] = False
        w["approvals"].pop(aid, None)
        if clear_verification:
            c.update(verification_value=None, verification_note="", verification_at="", scope_reviewed=False, production_reviewed=False, permit_reviewed=False)
        if c.get("work_order_id"):
            db.execute("UPDATE work_orders SET status='Open' WHERE id=? AND sid=? AND ds=?", (c["work_order_id"], s, a["id"]))
        for alert in a["result"]["alerts"]:
            if alert["asset"] == aid:
                db.execute("INSERT OR REPLACE INTO alert_status VALUES(?,?,?,?)", (s, a["id"], alert["key"], "Open"))

    @router.get("/workspace")
    def get_workspace(s=Depends(sid)):
        with S.transaction() as db:
            a, w = current(db, s)
            return snapshot(a, w)

    @router.put("/context")
    def put_context(data: Context, s=Depends(sid)):
        with S.transaction() as db:
            a, w = current(db, s); ctx = validate_context(data.model_dump(), a)
            if w["reservations"] or w["approvals"]: raise HTTPException(409, "Release case reservations and reopen approved proposals before replacing context.")
            w["context"] = ctx
            for aid in w["cases"]: invalidate(db, s, a, w, aid, True)
            event(w, "Context replaced", ", ".join(f"{k}: {len(v)}" for k, v in ctx.items()))
            persist(db, s, a, w)
            return snapshot(a, w)

    @router.post("/context/upload")
    async def context_upload(kind: str = Form(...), file: UploadFile = File(...), s=Depends(sid)):
        active(s)
        if kind not in Context.model_fields: raise HTTPException(422, "Choose a supported context dataset.")
        raw = await file.read(10*1048576+1)
        if len(raw) > 10*1048576: raise HTTPException(413, "Context files must be at most 10 MB.")
        try:
            if (file.filename or "").lower().endswith(".json"):
                value = json.loads(raw)
                rows = value if isinstance(value, list) else value[kind]
            else:
                df = A.read_upload(file.filename or "", raw)
                rows = json.loads(df.to_json(orient="records", date_format="iso"))
                rows = [{k: v for k, v in r.items() if v is not None} for r in rows]
            with S.transaction() as db:
                a, w = current(db, s)
                if w["reservations"] or w["approvals"]: raise HTTPException(409, "Release reservations and reopen approved proposals before changing context.")
                merged = {**w["context"], kind: rows}
                ctx = validate_context(Context.model_validate(merged).model_dump(), a)
                w["context"] = ctx
                for aid in w["cases"]: invalidate(db, s, a, w, aid, True)
                event(w, "Context file imported", f"{kind}: {file.filename}")
                persist(db, s, a, w)
                return snapshot(a, w)
        except (ValueError, KeyError, TypeError, ValidationError) as e:
            raise HTTPException(422, f"Context import failed: {str(e)[:1500]}")

    @router.patch("/cases/{aid:path}")
    def patch_case(aid: str, patch: CasePatch, s=Depends(sid)):
        with S.transaction() as db:
            a, w = current(db, s); eq = asset(a, w, aid); c = case(w, aid)
            fields = patch.model_dump(exclude_unset=True)
            if any(v is None and k != "verification_value" for k, v in fields.items()):
                raise HTTPException(422, "Only verification_value may be cleared with null; use an empty string for optional text.")
            if "disposition" in fields and fields["disposition"] not in ("", "Confirmed component issue", "Operating change", "Sensor issue", "No fault found"):
                raise HTTPException(422, "Choose a supported inspection disposition.")
            for f in ("due", "verification_at"):
                if fields.get(f): dt(fields[f])
            if fields.get("verification_at") and dt(fields["verification_at"]) < dt(eq["last"].replace(" UTC", "+00:00")):
                raise HTTPException(422, "Verification must follow the latest source observation.")
            if fields.get("verification_sensor") and fields["verification_sensor"] not in eq["sensors"]: raise HTTPException(422, "Select a scored sensor from this equipment.")
            changed = {k: v for k, v in fields.items() if c.get(k) != v}
            if changed:
                verification_only = all(k.startswith("verification_") for k in changed)
                investigation_changed = bool(c["finding"].strip()) and any(k in changed for k in ("owner", "disposition", "finding"))
                if not verification_only or c["closed"]: invalidate(db, s, a, w, aid, investigation_changed)
                c.update(fields)
                # A full form can contain stale verification and checked reviews. Never restore them after a scope change.
                if investigation_changed:
                    c.update(verification_value=None, verification_note="", verification_at="", scope_reviewed=False, production_reviewed=False, permit_reviewed=False)
                event(w, "Case updated", aid+": "+", ".join(changed))
                persist(db, s, a, w)
            return snapshot(a, w)

    @router.post("/cases/{aid:path}/{action}")
    def case_action(aid: str, action: str, s=Depends(sid)):
        if action not in ("reserve", "release", "approve", "close", "reopen"): raise HTTPException(404, "Unknown case action.")
        with S.transaction() as db:
            a, w = current(db, s); eq = asset(a, w, aid); c = case(w, aid); r = assessment(a, w, aid)
            if action == "reserve":
                if aid in w["reservations"]: raise HTTPException(409, "Materials are already reserved for this case.")
                m = materials(w, eq)
                if not m["ready"]: raise HTTPException(409, "Insufficient unreserved stock or missing BOM.")
                w["reservations"][aid] = {"part_id": m["part"]["part_id"], "qty": m["required"]}
            elif action == "release":
                w["reservations"].pop(aid, None); invalidate(db, s, a, w, aid)
            elif action == "approve":
                blockers = list(r["blockers"])
                if aid not in w["reservations"]: blockers.append("Reserve required materials for this case")
                if not all(c[k] for k in ("scope_reviewed", "production_reviewed", "permit_reviewed")): blockers.append("Complete scope, production and permit-prerequisite reviews")
                if c["disposition"] != "Confirmed component issue": blockers.append("A component repair proposal requires confirmed component findings")
                if blockers: raise HTTPException(409, "; ".join(blockers))
                win = r["candidate"]; c["approved"] = True
                w["approvals"][aid] = {"pool": win["resource_pool_id"], "start": win["proposed_start"], "end": win["proposed_end"], "crew": win["required_crew"], "window_id": win["window_id"]}
                if not c.get("work_order_id"):
                    cur = db.execute("INSERT INTO work_orders(sid,ds,title,asset,assignee,due,status) VALUES(?,?,?,?,?,?,?)", (s, a["id"], "Approved proposal: inspect / service "+aid, aid, c["owner"], win["proposed_start"][:10], "Open"))
                    c["work_order_id"] = cur.lastrowid
                else:
                    db.execute("UPDATE work_orders SET assignee=?,due=?,status='Open' WHERE id=? AND sid=? AND ds=?", (c["owner"],win["proposed_start"][:10],c["work_order_id"],s,a["id"]))
            elif action == "close":
                if not (c["owner"].strip() and c["finding"].strip() and c["disposition"] and c["verification_sensor"] and c["verification_value"] is not None and c["verification_note"].strip() and c["verification_at"]):
                    raise HTTPException(409, "Closure requires owner, disposition, findings, a sensor, verification reading, time and comparable operating conditions.")
                c["closed"] = True
                if c.get("work_order_id"):
                    db.execute("UPDATE work_orders SET status='Done' WHERE id=? AND sid=? AND ds=?", (c["work_order_id"], s, a["id"]))
                for alert in a["result"]["alerts"]:
                    if alert["asset"] == aid: db.execute("INSERT OR REPLACE INTO alert_status VALUES(?,?,?,?)", (s, a["id"], alert["key"], "Resolved"))
            elif action == "reopen": invalidate(db, s, a, w, aid)
            event(w, "Case "+action, aid)
            persist(db, s, a, w)
            return snapshot(a, w)

    @router.get("/cases/{aid:path}/pack")
    def pack(aid: str, s=Depends(sid)):
        with S.transaction() as db:
            a, w = current(db, s); eq = asset(a, w, aid)
            return {"asset_id": aid, "dataset": a["name"], "source_time": eq["last"], "evidence": eq["sensors"], "investigation": case(w, aid), "readiness": assessment(a, w, aid), "reservation": w["reservations"].get(aid), "approval": w["approvals"].get(aid), "dependencies": [d for d in w["context"]["dependencies"] if aid in (d["from_asset"], d["to_asset"])], "changes": [d for d in w["context"]["changes"] if d["asset_id"] == aid], "limits": ["No live execution", "No validated future failure probability", "No proved avoided downtime or ROI"], "audit": w["audit"]}

    @router.get("/knowledge")
    def knowledge(q: str = "", s=Depends(sid)):
        with S.transaction() as db:
            a, w = current(db, s)
            terms = q.lower().split()
            return [d for d in w["context"]["documents"] if all(t in " ".join(str(v) for v in d.values()).lower() for t in terms)]

    @router.post("/scenarios")
    def scenario(p: Scenario, s=Depends(sid)):
        with S.transaction() as db:
            a, w = current(db, s); base = assessment(a, w, p.asset_id); test = assessment(a, w, p.asset_id, p)
            eq = asset(a, w, p.asset_id); rate = eq.get("downtime_cost_per_hour")
            return {"baseline": base, "scenario": test, "assumptions": p.model_dump(), "estimated_shortfall_units": max(0, p.demand-p.standby_capacity)*p.hours if p.demand is not None and p.standby_capacity is not None else None, "estimated_interruption_cost": rate*p.hours if rate is not None else None, "limits": "Deterministic planning estimate. No degradation, physical cascade, supplier uncertainty, failure date or avoided-loss prediction. Scenario inputs do not update records or reserve resources."}

    app.include_router(router)
