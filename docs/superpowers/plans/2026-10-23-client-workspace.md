# SentinelOps Client Workspace Implementation Plan

> **For agentic workers:** Execute this approved preview in this session using superpowers:executing-plans. Keep a task ledger here and run tests before claiming completion.

**Goal:** Implement the approved client workspace, persist operational records and push a tested feature branch to the existing GitHub repository.

**Architecture:** Keep FastAPI, React/Vite and existing analytics/model endpoints. Add SQLite dataset persistence and a transactional workspace service for context, investigations, material reservations, shared crew checks, approval and verification. Replace the application shell with the approved horizontal navigation and connect every view to server data.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, SQLite, pandas, React 18, Vite 5, pytest, Playwright.

**Spec:** Approved `sentinelops-client-workspace-preview.html` and its case workflow, plus the existing repository README analytics definitions.

## Global Constraints

- Strict initial dataset gate. No automatic sample results or invented measurements.
- Preserve CSV/Excel mapping, chronological analytics, alerts, work orders and model training.
- Persist dataset and workflow state; use transactional resource allocation and session isolation.
- Emoji-free UI, responsive layout, accessible native controls, explicit unavailable states.
- No live connectors, predictive failure dates, physical cascade model or verified ROI claims.
- Push a feature branch; do not merge or manually deploy. Existing hosting integrations may create branch previews.

## Review Focus

- Concurrent reservations and shared crew approvals must not overbook resources.
- Context replacement and changed investigation evidence must not leave stale approvals.
- Invalid uploads must retain the current dataset and all saved work.
- Restart must restore active data and operational records without cross-session access.
- Failure-event exposure periods and incomplete costs must not generate misleading reliability metrics.

### Task 1: Durable dataset and validated context

Files: `backend/app/storage.py`, `backend/app/workspace.py`, `backend/app/main.py`, `backend/tests/test_workspace.py`.

- [x] Write/run failing API tests for persistence, atomic context validation, isolation and capabilities.
- [x] Implement durable active dataset storage and context imports (JSON bundle and CSV/Excel context files).
- [x] Run existing and new pytest tests.

### Task 2: Operational decisions and resource consistency

Files: `backend/app/workspace.py`, `backend/tests/test_workspace.py`.

Interfaces: `GET /api/workspace`, `PUT /api/context`, `PATCH /api/cases/{asset}`, `POST /api/cases/{asset}/{action}`, `POST /api/scenarios`, `GET /api/cases/{asset}/pack`.

- [x] Write/run failing tests for reservation conflicts, release, approval prerequisites, overlapping crew jobs, verified closure and invalidation.
- [x] Implement SQLite immediate transactions, audit records, case/work-order links and deterministic planning scenarios.
- [x] Test event metrics, source retrieval and export from actual context.

### Task 3: Approved application UI

Files: `frontend/src/App.jsx`, `frontend/src/Workspace.jsx`, `frontend/src/workspace.css`, `frontend/e2e/client-workspace.spec.js`.

- [x] Add failing browser coverage for context import and the full decision journey.
- [x] Implement all twelve approved sections with explicit data dependencies and server-backed actions.
- [x] Preserve original model/work-order tooling and telemetry upload workflow.
- [x] Verify empty, partial, invalid, full-context and mobile states; review rendered screenshots.

### Task 4: Review, documentation and GitHub delivery

- [x] Run full pytest, Playwright and production build. Review code/diff for security, regressions and metric correctness.
- [x] Document data contracts, persistence, limits and actual checks in README/change report.
- [x] Package an updated ZIP; commit and push `feature/sentinelops-client-workspace`; create/attach a reviewable PR if access permits.

## Execution Ledger

- Repository clean at `c1e7707`, current remote main. Branch created after user requested continuation following approval-review usage-limit failure.
- Ruling: use the existing dedicated task checkout and a new feature branch. No additional worktree needed.
- Ruling: implement without a further approval round because the user approved the detailed preview and explicitly requested build and push.
- Ruling: retain the existing anonymous session boundary and clearly document its limits; do not represent it as authenticated multi-user access control.

- Tasks 1–3: implemented. Backend suite 70/70 green; browser suite 23/23 green before the final alert-table refresh regression.
- Final review: independent read-only reviewer completed. Fixed stale verification/review fields, explicit null clearing, alert transaction race, linked-order owner/due refresh, operating-plus-repair exposure validation and sequential shared crew slots. Targeted RED→GREEN tests added.
- Final review: author screenshot pass found a stale alert table after case closure; added a browser assertion and keyed the alert component to workflow revision.
- Ruling: no optional GitHub Actions workflow added in this change; test commands, reports and existing hosting integrations retained.
- Ruling: retain single mapped part per asset case, record reservations without claiming stock consumption, and document this boundary.
- Final verification: 70 pytest tests passed (32.49 seconds), 23 Playwright tests passed (28.3 seconds), and the production Vite build succeeded.
- Delivered implementation commit `64395b6` on `feature/sentinelops-client-workspace`. Opened and attached PR https://github.com/AnkitJohari01/Predictive-maintainance/pull/3. The connector denied PR creation (403); the signed-in GitHub CLI succeeded.
- Created `sentinelops-client-workspace.zip` from tracked source and documentation, excluding local dependencies, databases and build outputs. Regenerate the archive after this delivery-note commit so it matches the final branch. No merge or manual deployment performed.
