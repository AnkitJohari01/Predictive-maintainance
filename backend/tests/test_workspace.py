import copy
import json
from concurrent.futures import ThreadPoolExecutor
from test_api import c, H, new, ready
from app.main import SESS
from app import storage as store
import pytest


def context(stock=1):
    return {
        "assets": [{"asset_id": a, "name": "Pump " + a, "site": "Plant", "criticality": "A", "owner": "Planner", "repair_hours": 2, "skill": "Mechanical", "part_id": "BRG", "part_qty": 1, "operating_hours": 100, "observation_start": "2026-09-01T00:00:00Z", "observation_end": "2026-10-01T00:00:00Z"} for a in "ABC"],
        "parts": [{"part_id": "BRG", "description": "Bearing", "on_hand": stock, "reserved": 0, "lead_days": 1, "unit_cost": 100}],
        "windows": [{"window_id": "WIN-" + a, "asset_id": a, "start": "2026-10-02T08:00:00Z", "end": "2026-10-02T12:00:00Z", "crew_skill": "Mechanical", "crew_count": 1, "required_crew": 1, "resource_pool_id": "POOL"} for a in "ABC"],
        "failures": [{"event_id": "F-1", "asset_id": "A", "failed_at": "2026-09-15T08:00:00Z", "restored_at": "2026-09-15T12:00:00Z", "failure_mode": "Bearing", "corrective_action": "Replace"}],
        "documents": [{"document_id": "D-1", "title": "Pump reference", "asset_class": "All", "revision": "A", "section": "1", "text": "Inspect bearing and verify comparable load."}],
        "dependencies": [{"from_asset": "A", "to_asset": "B", "service": "Cooling"}],
        "changes": [{"change_id": "CH-1", "asset_id": "A", "timestamp": "2026-09-20T08:00:00Z", "description": "Lubrication reviewed"}],
    }


def workspace(s):
    r = c.get("/api/workspace", headers=H(s)); assert r.status_code == 200, r.text
    return r.json()


def configure(s, stock=1):
    ready(s)
    r = c.put("/api/context", json=context(stock), headers=H(s)); assert r.status_code == 200, r.text


def investigate(s, asset="A"):
    p = {"owner": "Planner", "finding": "Bearing inspected under comparable load", "disposition": "Confirmed component issue", "scope_reviewed": True, "production_reviewed": True, "permit_reviewed": True}
    r = c.patch("/api/cases/" + asset, json=p, headers=H(s)); assert r.status_code == 200, r.text


def action(s, asset, name):
    return c.post(f"/api/cases/{asset}/{name}", headers=H(s))


def test_workspace_gate_and_missing_context():
    s = new(); assert c.get("/api/workspace", headers=H(s)).status_code == 409
    ready(s); w = workspace(s)
    assert not w["capabilities"]["planning"] and not w["context"]["parts"]
    assert w["reliability"]["mtbf_hours"] is None


def test_dataset_survives_memory_loss():
    s = new(); ready(s); before = c.get("/api/equipment", headers=H(s)).json()
    SESS.clear()
    assert c.get("/api/state", headers=H(s)).json()["unlocked"]
    assert c.get("/api/equipment", headers=H(s)).json() == before


def test_context_validation_atomic_and_session_scoped():
    s = new(); configure(s); bad = context(); bad["assets"][0]["asset_id"] = "UNKNOWN"
    assert c.put("/api/context", json=bad, headers=H(s)).status_code == 422
    assert workspace(s)["context"]["assets"][0]["asset_id"] == "A"
    other = new(); ready(other); assert workspace(other)["context"]["parts"] == []


def test_reservation_atomic_release_and_restart():
    s = new(); configure(s)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda a: action(s, a, "reserve"), ["A", "B"]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    SESS.clear(); w = workspace(s); assert len(w["reservations"]) == 1
    asset = next(iter(w["reservations"]))
    assert action(s, asset, "release").status_code == 200
    assert workspace(s)["reservations"] == {}


def test_approval_requires_findings_checklist_and_reserved_stock():
    s = new(); configure(s)
    assert action(s, "A", "approve").status_code == 409
    investigate(s); assert action(s, "A", "approve").status_code == 409
    assert action(s, "A", "reserve").status_code == 200
    assert action(s, "A", "approve").status_code == 200
    w = workspace(s); assert "A" in w["approvals"]
    assert c.get("/api/workorders", headers=H(s)).json()[0]["asset"] == "A"


def test_shared_crew_and_evidence_invalidation():
    s = new(); configure(s, 2)
    data=context(2)
    for window in data['windows']: window['end']='2026-10-02T10:00:00Z'
    assert c.put('/api/context',json=data,headers=H(s)).status_code == 200
    for a in "AB": investigate(s, a); assert action(s, a, "reserve").status_code == 200
    assert action(s, "A", "approve").status_code == 200
    assert action(s, "B", "approve").status_code == 409
    assert c.patch("/api/cases/A", json={"finding": "Changed work scope"}, headers=H(s)).status_code == 200
    assert "A" not in workspace(s)["approvals"]
    assert action(s, "B", "approve").status_code == 200


def test_verified_closure_and_alert_resolution_gate():
    s = new(); configure(s); investigate(s)
    alert = c.get("/api/alerts", headers=H(s)).json()[0]
    assert c.patch("/api/alerts/status", json={"key": alert["key"], "status": "Resolved"}, headers=H(s)).status_code == 409
    assert action(s, "A", "close").status_code == 409
    assert c.patch("/api/cases/A", json={"verification_sensor": "vibration", "verification_value": 2.1, "verification_note": "Same rpm and load", "verification_at": "2026-10-02T11:00:00Z"}, headers=H(s)).status_code == 200
    assert action(s, "A", "close").status_code == 200
    assert workspace(s)["cases"]["A"]["closed"]
    assert c.get("/api/alerts", headers=H(s)).json()[0]["status"] == "Resolved"
    c.patch("/api/cases/A", json={"verification_value": 2.2}, headers=H(s))
    assert not workspace(s)["cases"]["A"]["closed"]
    assert c.get("/api/alerts", headers=H(s)).json()[0]["status"] == "Open"


def test_context_change_rejects_active_reservations_without_explicit_reset():
    s = new(); configure(s); action(s, "A", "reserve")
    assert c.put("/api/context", json=context(2), headers=H(s)).status_code == 409
    assert len(workspace(s)["reservations"]) == 1


def test_reliability_uses_matched_period_and_no_fabricated_roi():
    s = new(); configure(s); r = workspace(s)["reliability"]
    assert r["mttr_hours"] == 4 and r["mtbf_hours"] == 300
    assert round(r["recorded_availability_pct"], 3) == round(100 * 300 / 304, 3)
    assert r["verified_savings"] is None
    bad = context(); bad["failures"][0]["failed_at"] = "2026-08-15T08:00:00Z"; bad["failures"][0]["restored_at"] = "2026-08-15T12:00:00Z"
    assert c.put("/api/context", json=bad, headers=H(s)).status_code == 200
    assert workspace(s)["reliability"]["mtbf_hours"] is None


def test_scenario_changes_no_operational_records_and_validates_inputs():
    s = new(); configure(s); before = copy.deepcopy(workspace(s))
    r = c.post("/api/scenarios", json={"asset_id": "A", "hours": 2, "demand": 80, "standby_capacity": 60}, headers=H(s))
    assert r.status_code == 200 and r.json()["estimated_shortfall_units"] == 40
    assert workspace(s)["reservations"] == before["reservations"]
    assert c.post("/api/scenarios", json={"asset_id": "A", "hours": -1}, headers=H(s)).status_code == 422


def test_export_pack_and_source_search():
    s = new(); configure(s); investigate(s)
    pack = c.get("/api/cases/A/pack", headers=H(s)).json()
    assert pack["asset_id"] == "A" and pack["investigation"]["owner"] == "Planner"
    assert c.get("/api/knowledge?q=bearing", headers=H(s)).json()[0]["document_id"] == "D-1"
    assert c.get("/api/knowledge?q=absent", headers=H(s)).json() == []


def test_complete_bundle_upload_and_invalid_replacement():
    s = new()
    data = {**context(), "telemetry": [{"timestamp": f"2026-09-{i+1:02d}", "asset_id": a, "vibration": 2+i*.01} for a in "ABC" for i in range(30)], "sensors": ["vibration"]}
    upload = lambda body: c.post("/api/bundles", files={"file": ("bundle.json", json.dumps(body).encode(), "application/json")}, headers=H(s))
    r = upload(data); assert r.status_code == 200, r.text
    assert workspace(s)["capabilities"]["planning"]
    action(s, "A", "reserve")
    data["parts"][0]["reserved"] = 99
    assert upload(data).status_code == 422
    assert "A" in workspace(s)["reservations"]


def test_missing_duration_blocks_approval_and_bad_pool_capacities_rejected():
    s = new(); configure(s)
    data = context(); data["assets"][0]["repair_hours"] = None
    assert c.put("/api/context", json=data, headers=H(s)).status_code == 200
    investigate(s); action(s, "A", "reserve")
    assert action(s, "A", "approve").status_code == 409
    action(s, "A", "release")
    data["windows"][1]["crew_count"] = 2
    assert c.put("/api/context", json=data, headers=H(s)).status_code == 422


def test_context_file_rejects_bad_reference_without_reset():
    s = new(); configure(s)
    r = c.post("/api/context/upload", data={"kind": "changes"}, files={"file": ("changes.csv", b"change_id,asset_id,timestamp,description\nC-1,UNKNOWN,2026-10-01,change")}, headers=H(s))
    assert r.status_code == 422
    assert workspace(s)["context"]["changes"][0]["change_id"] == "CH-1"


def test_multiple_parts_reservations_and_missing_financial_values():
    s = new(); configure(s, 2)
    assert action(s, "A", "reserve").status_code == 200
    assert action(s, "B", "reserve").status_code == 200
    assert action(s, "C", "reserve").status_code == 409
    assert workspace(s)["reliability"]["actual_spend"] is None


def test_asset_tag_with_slash_supports_case_actions():
    s = new(); ready(s, "timestamp,machine_id,vibration\n"+"\n".join(f"2026-09-{i+1:02d},PLANT/PUMP,{2+i*.01}" for i in range(30)))
    r = c.patch('/api/cases/PLANT%2FPUMP', json={"owner": "Planner"}, headers=H(s))
    assert r.status_code == 200, r.text
    assert c.get('/api/cases/PLANT%2FPUMP/pack', headers=H(s)).json()["asset_id"] == "PLANT/PUMP"


def test_stale_model_result_cannot_replace_new_dataset():
    s = new(); ready(s); old = store.load_dataset(s)
    ready(s); current = store.load_dataset(s)
    assert old['id'] != current['id']
    with pytest.raises(ValueError, match='changed'):
        store.save_model(s, old['id'], {"trained": True})
    assert store.load_dataset(s)['id'] == current['id']


def test_full_form_patch_cannot_reuse_verification_after_changed_findings():
    s = new(); configure(s); investigate(s)
    verification = {"verification_sensor": "vibration", "verification_value": 2.1, "verification_note": "Same speed and load", "verification_at": "2026-10-02T11:00:00Z"}
    c.patch('/api/cases/A', json=verification, headers=H(s)); assert action(s, 'A', 'close').status_code == 200
    patch = {**verification, "finding": "Different fault found", "scope_reviewed": True, "production_reviewed": True, "permit_reviewed": True}
    r = c.patch('/api/cases/A', json=patch, headers=H(s)); assert r.status_code == 200
    record = workspace(s)['cases']['A']
    assert record['verification_value'] is None
    assert not any(record[k] for k in ('scope_reviewed','production_reviewed','permit_reviewed'))
    assert action(s, 'A', 'close').status_code == 409


def test_linked_work_order_cannot_bypass_verification():
    s = new(); configure(s); investigate(s); action(s, 'A', 'reserve'); action(s, 'A', 'approve')
    wid = workspace(s)['cases']['A']['work_order_id']
    r = c.patch(f'/api/workorders/{wid}', json={'status': 'Done'}, headers=H(s))
    assert r.status_code == 409
    c.patch('/api/cases/A', json={'verification_sensor':'vibration','verification_value':2.1,'verification_note':'Same load','verification_at':'2026-10-02T11:00:00Z'}, headers=H(s))
    assert action(s,'A','close').status_code == 200
    assert c.get('/api/workorders',headers=H(s)).json()[0]['status'] == 'Done'


def test_reopening_alert_reopens_verified_case_and_clears_approval():
    s = new(); configure(s); investigate(s); action(s,'A','reserve'); action(s,'A','approve')
    c.patch('/api/cases/A', json={'verification_sensor':'vibration','verification_value':2.1,'verification_note':'Same load','verification_at':'2026-10-02T11:00:00Z'}, headers=H(s))
    action(s,'A','close')
    alert = c.get('/api/alerts',headers=H(s)).json()[0]
    assert c.patch('/api/alerts/status',json={'key':alert['key'],'status':'Open'},headers=H(s)).status_code == 200
    w=workspace(s)
    assert not w['cases']['A']['closed'] and 'A' not in w['approvals']


def test_clearing_verification_reading_invalidates_closed_case():
    s=new(); configure(s); investigate(s)
    c.patch('/api/cases/A',json={'verification_sensor':'vibration','verification_value':2.1,'verification_note':'Same load','verification_at':'2026-10-02T11:00:00Z'},headers=H(s)); action(s,'A','close')
    assert c.patch('/api/cases/A',json={'verification_value':None},headers=H(s)).status_code == 200
    assert workspace(s)['cases']['A']['verification_value'] is None
    assert not workspace(s)['cases']['A']['closed']


def test_shared_pool_uses_next_available_slot_inside_window():
    s=new(); configure(s,2)
    for a in 'AB': investigate(s,a); action(s,a,'reserve')
    assert action(s,'A','approve').status_code == 200
    assert action(s,'B','approve').status_code == 200
    approvals=workspace(s)['approvals']
    assert approvals['B']['start'] == approvals['A']['end']


def test_exposure_cannot_exceed_period_when_repair_time_is_included():
    s=new(); ready(s); data=context()
    for a in data['assets']: a['operating_hours']=720
    assert c.put('/api/context',json=data,headers=H(s)).status_code == 422


def test_reapproval_updates_linked_order_owner():
    s=new(); configure(s); investigate(s); action(s,'A','reserve'); action(s,'A','approve')
    c.patch('/api/cases/A',json={'owner':'New planner'},headers=H(s))
    c.patch('/api/cases/A',json={'scope_reviewed':True,'production_reviewed':True,'permit_reviewed':True},headers=H(s))
    assert action(s,'A','approve').status_code == 200
    assert c.get('/api/workorders',headers=H(s)).json()[0]['assignee'] == 'New planner'
