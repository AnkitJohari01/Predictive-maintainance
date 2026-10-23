# SentinelOps client workspace — change and test report

23 October 2026 · Existing repository: AnkitJohari01/Predictive-maintainance · Feature branch: feature/sentinelops-client-workspace.

## Implemented from the approved preview

- Responsive horizontal navigation and light/dark/system appearance across twelve sections. Production starts empty; illustrative data is not loaded automatically.
- Original CSV/Excel telemetry mapping, quality checks, statistical analytics, charts, alert decisions, work orders and chronological model training retained.
- Complete JSON bundle imports and individually validated operational context tables. Failed replacements preserve active data and saved work.
- SQLite persistence for datasets, model results, context, cases, reservations, approvals and audit; pending uploads remain temporary.
- Daily action desk with accountable owner, evidence, readiness blockers and case handoff.
- Case investigations, required production/scope/permit-prerequisite reviews, transactional material allocations, shared crew feasibility and linked work orders.
- Earliest fitting shared-crew slot search at window start and booking ends; peak simultaneous capacity checked. No global optimization is claimed.
- Verified case closure, related alert resolution and linked order completion. Changed findings clear old verification/reviews. Explicitly clearing a verification reading invalidates closure. Reopened alerts reopen the case.
- Source-linked uploaded reference retrieval, dependency and change views, work-pack/CSV exports, deterministic preparation/production scenarios and actual event/exposure/cost reporting.
- Missing evidence remains unavailable; scenario estimates do not become claimed savings or failure predictions.

## Verification

- Full backend suite: **70 pytest tests passed**. Includes all 46 existing tests plus persistence, complete-bundle validation, isolation, concurrent reservations, release/reopen, shared capacity and sequential slots, exposure integrity, verified closure, stale evidence, stale model writes, linked orders, slash-containing tags, scenario calculations and source retrieval.
- Browser suite: **23 Playwright Chromium tests passed in 28.3 seconds**, covering original workflows plus complete context, persistent case decisions after reload, allocation conflicts, approval, verified outcomes, scenarios, sources, invalid replacement and responsive layouts. The final run includes immediate alert-status refresh after case closure.
- Final backend run: **70 passed in 32.49 seconds**. Production Vite build succeeded. Local screenshots use uploaded test fixtures; no customer information is included.
- One Python dependency deprecation warning (Starlette/AnyIO portal alias) and browser runner color-environment warnings; neither produced a test failure.
- Independent read-only review identified stale verification, alert-write race, stale linked ownership, impossible exposure totals and missed sequential crew slots. Each issue was fixed; targeted failing regressions were observed before the fixes. Author also checked the final diff and rendered screens.

## Operational boundaries

Authentication/role authorization, live CMMS/historian integrations, physical cascading-failure models, calibrated future-failure forecasts, LLM RAG, multi-component job BOMs, warehouse consumption and procurement execution are not included. The retained X-Session browser token is not authenticated user identity. Use a trusted/private installation until proper authorization exists.

SQLite must be stored on durable host storage and backed up. It survives process restart, not loss of an ephemeral hosting filesystem. This version targets a single application instance. No manual deployment or merge is part of this delivery; existing GitHub hosting integrations can independently create branch/PR previews.

See `docs/CONTEXT_SCHEMA.md` for data fields, formulas, import ordering, exact action semantics and limits.

---

## Historical report from the prior release

The following record describes the previous dataset-validation update, not the current persistence architecture.

# SentinelOps change and test report

Completed 23 October 2026 (Asia/Calcutta). Updated the application supplied in `sentinelops.zip` in place. No deployment, repository reset, or source-file deletion was performed. The original attached archive remains unchanged.

## Previous dataset-validation release

| Area | Result |
| --- | --- |
| Dataset gate | Only Dataset setup is usable before successful validation and processing. Business API endpoints also enforce the gate. Navigation waits for processing to finish. Clear and backend dataset loss relock the workspace. |
| Upload validation | Clear errors for unsupported/corrupt/empty files, duplicate/blank headers, unknown or conflicting column mappings, too few clean rows, bad timestamps, missing asset IDs, unusable sensors and invalid failure flags. CSV, XLSX and XLS readers retained; the missing XLS dependency was added. |
| State preservation | Invalid uploads cannot reuse an older pending file. Failed replacement validation retains the active dataset, model and workflow records. Successful replacement invalidates old results and workflow records. |
| Dynamic analytics | KPIs, fleet counts, status/search filters, equipment evidence, alerts, recommendations and trained-model results come from the active upload. Missing evidence produces explicit unavailable/unscored states. No automatic demo dataset. |
| Charts | Elapsed-time axis, baseline and upper/lower critical bounds, hover inspection, accessible reading slider, UTC dates, and at most 200 representative points with the first/latest values preserved. |
| Model correctness | Equal timestamps remain together in chronological validation. Missing model features use training-period medians. Derived feature names cannot overwrite uploaded sensors. Metrics describe observed failure classification, not an unsupported failure forecast. |
| Workflows | Alert acknowledgement/resolution, inspection recommendations, work-order creation, assignment, due dates/status and training remain available. Work-order titles, assets, statuses and dates are validated. |
| UI | Responsive light operations workspace, consistent typography/spacing, labelled condition indicators, clearer setup/quality screens, visible focus, skip link and no authored emojis. Condition index explicitly distinguished from failure probability. |
| Request handling | Stale page loads cannot replace newer requests. Equipment load errors are displayed. Backend connection retry is available. Dataset-loss responses return the app to upload. |
| Test configuration | Playwright uses the local Python environment, isolated temporary workflow database, fresh local servers, failure traces/screenshots and an HTML report. Pytest works from the backend directory without a separate path setting. |

## Verification results

Final runs on Windows, Python 3.10.11. No skipped tests or outstanding test failures.

| Check | Result |
| --- | --- |
| Full pytest suite | **46 passed**, 8.92 seconds |
| Full Playwright Chromium suite | **20 passed**, 19.0 seconds |
| Frontend production build | **Passed**, 31 modules; JavaScript 170.03 kB (53.98 kB gzip), CSS 8.94 kB (2.66 kB gzip) |
| Browser errors and emojis | No uncaught browser errors on the navigation review; no emojis in visited page text |
| Mobile layout | 390 px viewport, no document-level horizontal overflow; navigation and sensor chart usable; wide tables scroll within their container |
| Visual review | Desktop upload and equipment screens, plus the mobile overview, inspected from real browser screenshots |

The first expanded backend run against the supplied code had 16 failures and 23 passes, exposing validation/state defects. A later numeric-timestamp regression also reproduced silent date misinterpretation before its fix. Browser testing reproduced missing filter/chart interactions and a processing-navigation timing issue. Those paths pass in the final runs.

Coverage includes initial locking; successful CSV and XLSX processing; invalid extensions and corrupt Excel; empty/short/mostly-invalid data; mapping correction; cleaned row counts; non-finite measurements; failure labels; offsets and asset IDs containing slashes; unavailable/unscored results; search/status filters; chart sensor switching and exact first/latest readings; alert decisions; work-order lifecycle and session scoping; replacement preservation/reset; clear/relocking; supervised and unsupervised models; same-timestamp validation; mobile navigation; and restart-like dataset loss.

Two browser tests intentionally intercept responses to simulate processing and equipment-service errors and verify recovery. The remaining workflow checks use the real local backend. The review screenshots use an explicitly uploaded repository test fixture, and are not presented as customer results.

Non-failing dependency warnings: Starlette emits one AnyIO deprecation warning during pytest; the Playwright runner emits a terminal-color environment warning. Neither prevented test execution. No security audit, dependency vulnerability audit or load test was performed.

## Included evidence

- `docs/pytest-results.xml`: final machine-readable pytest result.
- `docs/playwright-report/index.html`: final browser test report; open in a browser.
- `docs/previews/upload-desktop.png`: initial locked state.
- `docs/previews/overview-desktop.png`: uploaded fixture analytics.
- `docs/previews/equipment-desktop.png`: sensor trend and evidence.
- `docs/previews/overview-mobile.png`: responsive overview.
- `README.md`: installation, data contract, methodology, test commands and operational limits.

## Remaining operational limits

The application still requires authentication/authorization and durable shared dataset/session storage before public multi-user production use. Anonymous session tokens and per-process memory were present in the original application and remain; use one backend worker locally. Uploaded data/model results disappear after restart. Quotas, retention/backup policy, upload scanning and coordinated concurrent mutations require further infrastructure work.

Remaining useful life, cost impact, parts inventory, production-aware scheduling, manuals/RAG and drift monitoring were absent from the supplied implementation and are not invented. Models classify uploaded labels and statistical shifts; no calibrated future-failure probability is claimed. Optional MLflow service connectivity, legacy XLS fixtures, non-Chromium browsers and production hosting were not tested.

## Delivery

The updated ZIP contains the full source, dependency manifests, original sample generator, tests, instructions, this report and evidence. Installed dependencies, virtual environments, build output, runtime databases and caches are excluded. Nothing was deployed.
