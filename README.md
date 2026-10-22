# SentinelOps

Dataset-first predictive maintenance platform. Python/FastAPI backend, React (Vite) frontend, SQLite for alert status and work orders, MLflow for experiment tracking, Pytest and Playwright for tests.

The app is locked until a dataset passes upload, column mapping and quality checks. Every number shown is computed from the active dataset. Anything the data cannot support is shown as "Insufficient data" with a reason.

## Run
```
cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev        # http://localhost:5173
python backend/scripts/make_sample.py sample.csv # optional sample data
```
## Test
```
cd backend && python -m pytest -q
cd frontend && npx playwright install chromium && npx playwright test
```

## How status is calculated
For each machine and sensor, the baseline is the mean and standard deviation of the first 60% of that machine's readings. The shift is the mean of the last 3 readings minus the baseline, in standard deviations. 1.5 or more is Watch, 3 or more is Critical. This is a statistical rule, not a trained model, and does not estimate failure dates.

The ML Monitor trains a model only on request, using a time-ordered split (earlier 70% train, later 30% test). Missing features use medians learned only from the training period, with zero as the fallback for an entirely missing training feature. With a failure column it trains a class-balanced Random Forest and needs 3+ flagged rows in the training period and 1+ in the test period, plus at least one non-failure training row. These are row flags, not deduplicated failure episodes. Without a failure column it trains an Isolation Forest and reports no accuracy. Model training does not change the statistical equipment scores or alerts.

## Input validation
- CSV and Excel equipment IDs are read as text, preserving `001` separately from `1` and literal IDs such as `NA`. Excel IDs must be stored as text; numeric cell formatting is not an identity source.
- Headers must be non-empty and unique after trimming. Mapped roles must exist and be distinct.
- A mapped failure column must contain only `0`, `1`, `0.0`, `1.0`, `true` or `false` (case-insensitive, surrounding whitespace ignored). Missing or unknown flags block processing; correct them or leave the failure role unmapped. Unknown values are never silently counted as zero.
- Sensor infinities, exponent overflow and calculations outside finite numeric range are rejected. Model features must also fit the tree estimators' float32 numeric range.
- Quality missingness includes empty cells and mapped sensor values that cannot be converted to numbers. Literal equipment IDs remain intact. Quality counters can overlap and are not additive row-removal totals.
- Duplicate detection uses normalized mapped numeric sensors and binary flags, so equivalent readings such as `100`/`100.0` are not counted twice. Equipment IDs remain text.
- Alert keys are opaque encoded equipment/sensor pairs; clients should echo the returned key instead of building one.
- Work orders require a nonblank title; an optional equipment reference must belong to the active dataset. Due dates must be real ISO dates or empty to clear; status must be Open, In progress or Done. Multi-field edits are atomic.

A ready-to-enable GitHub Actions template is provided in [docs/qa-workflow.example.yml](docs/qa-workflow.example.yml). It remains inactive until copied to `.github/workflows/qa.yml` by an account with workflow permission; the available publishing login lacks that scope. Playwright starts dedicated local servers and uses a separate temporary SQLite database. Set `SENTINELOPS_PYTHON` to an absolute Python interpreter path if it is not `python` on PATH. See [QA improvement notes](docs/QA-IMPROVEMENTS.md) for validation scope and remaining decisions.

## Known limitations
- Uploaded datasets live in server memory per session (X-Session header). They are lost on restart; alert status and work orders are stored in SQLite but belong to a dataset that no longer exists after a restart, so the app starts locked again.
- There is no user authentication. The session id is an anonymous browser token, so it isolates sessions but is not a security boundary.
- Drift monitoring, remaining-useful-life estimation and cost impact are not implemented.
- XLSX upload has an automated identity-preservation test. Legacy `.xls` requires `xlrd`, which is not included in the default requirements and has not been validated.
- Charts show at most 200 points per sensor, retaining the first and latest valid reading. Both positive and negative critical boundaries are shown. Alert data time is the triggering sensor's latest valid reading.
- Model metadata is retained only in memory; the fitted estimator and row-level predictions are not persisted. MLflow logging is optional and requires an extra installation/configuration.
