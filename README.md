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
cd backend && pytest -q
cd frontend && npx playwright install chromium && npx playwright test
```

## How status is calculated
For each machine and sensor, the baseline is the mean and standard deviation of the first 60% of that machine's readings. The shift is the mean of the last 3 readings minus the baseline, in standard deviations. 1.5 or more is Watch, 3 or more is Critical. This is a statistical rule, not a trained model, and does not estimate failure dates.

The ML Monitor trains a model only on request, using a time-ordered split (earlier 70% train, later 30% test). With a failure column it trains a class-balanced Random Forest and needs 3+ failure events in the training period and 1+ in the test period. Without one it trains an Isolation Forest and reports no accuracy.

## Known limitations
- Uploaded datasets live in server memory per session (X-Session header). They are lost on restart; alert status and work orders are stored in SQLite but belong to a dataset that no longer exists after a restart, so the app starts locked again.
- There is no user authentication. The session id is an anonymous browser token, so it isolates sessions but is not a security boundary.
- Drift monitoring, remaining-useful-life estimation and cost impact are not implemented.
- Excel upload is implemented (openpyxl) but has no automated test yet.
- Charts show up to about 200 points per sensor (downsampled).
