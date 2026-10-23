# SentinelOps improvement plan

User scope: improve the supplied application in place, preserve workflows, enforce the upload gate, use actual uploaded data, validate errors, remove emojis, test with pytest and Playwright, and deliver a ZIP. No deployment or destructive operations.

1. Add regression tests for invalid mappings, non-finite values, malformed failure labels, empty equipment IDs, insufficient clean data, Excel uploads, model validation and work-order inputs. Run against the original code to confirm the gaps.
2. Centralize validation and cleaning in `backend/app/analytics.py`; keep the current baseline method and API contracts. Harden API inputs and time-based model preprocessing in `backend/app/main.py`.
3. Preserve React navigation, alerts, work orders and training. Make loading/error states race-safe, relock when the backend loses its dataset, add interactive sensor charts and status filtering, and improve setup and responsive layouts.
4. Expand real-browser tests for uploads, validation, mapping, navigation, filters, charts, maintenance, training, replacement and clearing. Run all backend tests, browser tests and the production build.
5. Document the data contract, methodology, remaining operational limits and exact test results. Package source and reports without dependencies, caches or runtime data.

Design: light industrial operations workspace; white surfaces (#ffffff), slate text (#172b3a), pale background (#f3f6f8), blue action (#205bd7), teal healthy (#137d69), red critical (#b42318). System UI typography, clear left alignment, compact navigation, comfortable table rows, restrained borders, visible keyboard focus, and mobile stacking. Status always has a text label. No sample analytics appear before upload. Health is explicitly a baseline condition index, never a failure probability.

Review focus: failed replacements retain the active dataset; invalid upload attempts cannot reuse an older pending file; timestamps with offsets normalize consistently; low-information datasets never produce invented health or model metrics; backend restarts return the UI to upload.
