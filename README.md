# SentinelOps

Dataset-first equipment condition analysis and maintenance workflow application. Existing FastAPI, React/Vite, SQLite, baseline analytics, alert decisions, work orders, model training and optional MLflow integration are retained.

## Start locally

Requires Python 3.10+ and Node.js 18+ (Node.js 20+ recommended). Create a virtual environment in this project root.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open http://127.0.0.1:5173. On macOS/Linux, use `.venv/bin/python` instead of `.venv\Scripts\python.exe`. The frontend development proxy sends `/api` requests to the backend on port 8000. `npm run build` creates frontend static files; a production host must route `/api` to FastAPI. No deployment was performed.

## Upload workflow and data contract

Only the Dataset setup screen is accessible until upload, column validation and processing succeed. The server also rejects direct business API access without an active dataset. Select a CSV (UTF-8), XLSX or XLS file, match columns, check data quality, then choose **Process and unlock**. No example data is loaded automatically.

- Required: timestamp, equipment ID, and at least one numeric sensor column. Mapping is editable; column names need not match the example.
- Headers must be unique and non-empty, including after whitespace trimming.
- Timestamps must be dates, Excel date cells or ISO strings. Offset timestamps normalize to UTC; timezone-free values are interpreted as UTC. Convert numeric epoch or Excel serial values into dates first. All displayed times are UTC.
- At least 20 usable unique rows must remain after cleaning. Each equipment/sensor needs 10 numeric readings for baseline scoring. Assets below that threshold remain explicitly unscored.
- Duplicate rows, invalid timestamps, missing/blank equipment IDs and rows with no usable selected sensor are excluded. Missing, nonnumeric, non-finite and implausibly large sensor values (absolute value above 1e100) are excluded from calculations. Uploaded sensor history is never imputed.
- Up to 30% unreadable timestamps are allowed and reported as excluded rows. Above that, processing is blocked.
- Failure labels are optional. If mapped, every value must be 0/1 or true/false (case-insensitive). Missing/unknown labels block processing; they are never counted as healthy. Choose None to omit labels.
- Limits default to 50 MB per file; set `SENTINELOPS_MAX_MB` to override. The setup screen states the default limit; the server enforces its configured limit.
- Put measurement units in sensor headers. The app does not assume or convert units.

A failed replacement keeps the active dataset, work orders, alert decisions and trained model. A failed upload invalidates any older pending upload, preventing accidental processing of the wrong file. A successful replacement or Clear dataset resets derived state and associated workflow records. Clearing relocks navigation. A backend dataset-loss response also returns the frontend to upload.

The repository includes `backend/scripts/make_sample.py` and `frontend/e2e/sample.csv` for explicit testing only. Screenshot analytics in `docs/previews` come from uploading that test fixture, not from a customer dataset.

## Analytics and model interpretation

Each equipment/sensor baseline uses the first 60% of its chronological readings. Recent value is the last three valid readings' mean. Standard deviation is floored at the larger of 1% of the baseline mean magnitude and 1e-6 to handle constant signals. A shift of at least 1.5 standard deviations in either direction is Watch; at least 3 is Critical.

The displayed condition index is `100 - min(100, round(abs(largest_z_shift) * 25))`. It is a heuristic condition indicator, not calibrated health or a failure probability. It is unavailable for unscored equipment. Alerts and inspection recommendations expose the supporting readings. Charts preserve the first and latest readings and show at most 200 representative points on an elapsed-time axis, with hover and keyboard inspection and both critical bounds.

ML Monitor trains only on request. Roughly the earlier 70% of distinct timestamps train the model; later timestamps validate it. Equal timestamps stay in the same partition. Rolling sensor means use present/past readings, and missing model features use training-period medians (zero only when a training feature is entirely missing).

With failure labels, a class-balanced Random Forest classifies observed flags and reports held-out precision, recall, ROC-AUC and confusion counts. At least three positive training rows, one positive test row and both training classes are required. These are contemporaneous labels; metrics are not validated future failure predictions. Without labels, Isolation Forest reports the unusual-reading share without inventing accuracy. Retraining replaces the active model result. Optional MLflow logs training parameters and scalar metrics when installed and configured; the app reports logging failures.

## Tests and build

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm ci
npx playwright install chromium
npm run e2e
npm run build
```

Playwright automatically uses the project virtual environment when present. Override `SENTINELOPS_PYTHON` for another interpreter. It starts fresh local servers, uses an isolated temporary SQLite database, and refuses to reuse an already running server on ports 8000/5173. Stop your local development servers before running it. Reports: `frontend/playwright-report/index.html`; screenshots and traces are retained for failures. Review screenshots are regenerated in `docs/previews` by the review test. See `CHANGE_TEST_REPORT.md` for actual results and scope.

## Operational limits before production use

This update improves correctness and UI quality but is not a complete production infrastructure rollout:

- There is no authentication or authorization. The anonymous `X-Session` token is browser state, not a user identity or security boundary. Add authenticated access before exposing sensitive data.
- Uploaded data and model results are held in one server process's memory and disappear on restart. Use one backend worker for this version; multi-worker/multi-instance use needs shared durable dataset/session storage and coordinated mutations.
- SQLite retains work orders and alert decisions, scoped to a transient dataset. Configure `SENTINELOPS_DB` for its path. A production retention/backup policy, quotas, expiry and upload scanning are not implemented.
- The baseline is statistical, sensitive to operating regimes and sampling. Models are evaluated against uploaded labels; neither is a certified maintenance safety system.
- Remaining useful life, cost savings, parts inventory, production-aware scheduling, manual retrieval/RAG and drift monitoring were not implemented in the supplied app and are not fabricated here.
- Automated browser coverage uses Chromium. XLSX and CSV are exercised; the XLS reader dependency is included but a legacy XLS fixture is not covered. Optional MLflow service connectivity, load testing and production hosting have not been tested.
