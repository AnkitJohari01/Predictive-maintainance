# Operational data contract

The application opens with Data setup only. Upload CSV / XLSX / XLS telemetry through column mapping, or upload a complete JSON bundle. Nothing loads automatically.

## Complete JSON bundle

`telemetry` is an array of wide records, one row per equipment timestamp. A bundle accepts `sensors` (sensor column names) and optional `mapping` (`timestamp`, `id`, `failure`, `sensors`). Omit mapping for column inference. It also accepts the eight context arrays below. Unknown sections, invalid relationships or invalid telemetry reject the entire replacement. Existing data and saved workflows stay intact on failure.

```json
{
  "telemetry": [
    {"timestamp": "2026-10-01T08:00:00Z", "asset_id": "P-104", "vibration_mm_s": 2.1}
  ],
  "sensors": ["vibration_mm_s"],
  "assets": [], "parts": [], "windows": [], "orders": [],
  "failures": [], "documents": [], "dependencies": [], "changes": []
}
```

This illustrates structure only: at least 20 usable unique telemetry rows and 10 measurements per scored equipment/sensor are required. Units belong in sensor names. Do not supply readings invented for a real asset.

## Context tables

After telemetry processing, Data setup accepts a complete context JSON object with these arrays, or one table via CSV, Excel or JSON. Individual JSON may be an array or an object containing the selected table key. Complete replacement is available in the expandable JSON editor. A downloadable structural template is provided; replace its identifiers and values with actual records before importing.

| Table | Required fields | Optional fields |
|---|---|---|
| `assets` | `asset_id` | `name`, `site`, `line`, `asset_class`, `criticality` (A/B/C/Unknown), `owner`, `part_id`, `part_qty` (positive integer), `repair_hours` (positive), `skill`, `downtime_cost_per_hour`, `operating_hours`, `observation_start`, `observation_end` |
| `parts` | `part_id`, `on_hand`, `lead_days` | `description`, `reserved` (default 0), `min_stock`, `unit_cost`, `supplier` |
| `windows` | `window_id`, `asset_id`, `start`, `end`, `crew_skill`, `crew_count`, `required_crew` | `resource_pool_id`, `production_state` |
| `orders` | `work_order_id`, `asset_id`, `title`, `status` | `assignee`, `due_at`, `estimated_hours`, `labor_cost`, `material_cost`, `closed_at`, `priority` |
| `failures` | `event_id`, `asset_id`, `failed_at`, `restored_at` | `failure_mode`, `corrective_action` |
| `documents` | `document_id`, `title`, `revision`, `section`, `text` | `asset_class` (default All) |
| `dependencies` | `from_asset`, `to_asset`, `service` | `source` |
| `changes` | `change_id`, `asset_id`, `timestamp`, `description` | — |

Unknown fields are rejected so misspelled inputs do not silently disappear. IDs must be unique where a record ID is defined. Equipment references must occur in telemetry. Import stock before a separately uploaded asset table that references it; a complete context object can import both together.

All dates normalize to UTC; timezone-free timestamps are interpreted as UTC. End times must follow start times. `operating_hours` requires observation start/end, and operating hours plus recorded downtime must fit that interval. Failure intervals cannot overlap for the same asset. Events outside observation periods remain visible but make cohort MTBF/availability unavailable. Stock and quantity values are nonnegative integers; imported reserved stock cannot exceed on-hand stock. Monetary values in this version use INR consistently.

## Case decisions and resources

- PATCH `/api/cases/{asset}` records owner, review due date, disposition, findings, review checkboxes and verification. Supported dispositions: Confirmed component issue / Operating change / Sensor issue / No fault found.
- POST `/api/cases/{asset}/reserve` atomically holds the mapped part quantity. Imported allocations are retained. Competing requests cannot allocate stock twice.
- POST `/api/cases/{asset}/release` removes this case's allocation and invalidates its approval.
- POST `/api/cases/{asset}/approve` requires owner, confirmed component findings, recorded duration/skill, reserved materials, a fitting window, identified shared crew pool and scope/production/permit-prerequisite review. It creates or updates a linked work order. This is a planning approval, not a site work permit or equipment control command.
- Shared pool windows must agree on capacity/skill where they overlap. The earliest fitting interval is considered at window start and existing booking ends; peak simultaneous demand is checked. This is deterministic feasibility checking, not global schedule optimization or named technician dispatch.
- POST `/api/cases/{asset}/close` requires disposition, findings, owner, a scored verification sensor, nonnegative reading, verification time after source observation and comparable-operating-conditions note. It resolves related alerts and completes a linked order, without altering raw readings or adding failure labels.
- Changing investigation findings/owner/disposition clears old verification and review checks. Reopening a case or its resolved alert removes approval. Clearing a verification reading with JSON null reopens a closed case. Linked work orders cannot bypass verification through the older status endpoint.
- GET `/api/cases/{asset}/pack` exports evidence, decision record, reservation, approval, relationships, changes and audit history.
- Context changes require releasing reservations and reopening approvals first, and invalidate verification. This avoids silent changes to active commitments. Successful telemetry replacement intentionally resets its context, workflow and model; failed replacement preserves everything.

Current material model is one mapped part per asset case. Multi-component job BOMs, receipt/issue accounting and procurement integrations need a later implementation. Reservations do not claim actual stock consumption. Close/reopen/release semantics are recorded in the audit trail.

## Scenarios, knowledge and outcomes

POST `/api/scenarios`: `asset_id`, `hours`, optional `delay_days`, `lead_days`, `stock`, `crew`, `demand`, `standby_capacity`. Empty inputs use recorded resource context where available. Scenarios never write operational records. Shortfall = max(0, demand − standby capacity) × duration, assuming constant demand and no production recovery. Interruption cost = supplied hourly rate × duration. Both are estimates, not prevented loss. A hypothetical part arrival is not actual stock or permission to approve a job.

GET `/api/knowledge?q=...` retrieves uploaded source text by keyword matching, with record ID, revision and section. Missing sources return an empty list. No LLM, web retrieval, OEM validation or automatic diagnosis is represented.

Reliability uses recorded failure/restoration intervals and valid operating exposure. Mean recorded repair time is not necessarily hands-on repair labor. MTBF = operating hours / matched failures. Recorded availability = operating / (operating + matched repair hours); it is not scheduled production availability. Actual spend uses completed imported work with both labor/material fields. Missing costs remain unavailable. Avoided outages, causal uptime improvement, protected revenue and verified ROI are not fabricated.

## Persistence and access

SQLite stores active telemetry, analytics, model result, context, decisions, reservations, approvals and audit. Set `SENTINELOPS_DB` to a durable file path and back it up. Local disk persistence survives process restarts; ephemeral hosting disks do not survive redeploys. A shared database service is required for multi-instance deployment.

The existing browser-generated `X-Session` identifier is a data-scoping token, not authenticated user identity or role authorization. No authentication was added in this change. Use a trusted/private installation until a proper identity provider and authorization layer are implemented. Never put sensitive customer records in public example files.
