# QA improvements

Changes prepared from the SentinelOps QA discovery on 22 October 2026. Base revision: `187840c0e61d0cf3edcb3899ebd6ff9539843876`.

## Corrected behavior

| Area | Before | After |
|---|---|---|
| Schema validation | A mixed valid/missing sensor mapping caused HTTP500; duplicate headers could be renamed silently or crash inference | Check/Process reject unknown roles with422; upload rejects blank/duplicate normalized headers with400 |
| Equipment identity | CSV/XLSX parsing merged `001` and `1`, and dropped literal `NA` IDs | Text IDs survive ingestion; wholly numeric columns are excluded from timestamp inference; normalized numeric duplicates do not inflate counts |
| Failure labels | Unknown/missing manually mapped labels became negative rows | Processing blocks with an actionable error; documented binary vocabulary allows case/whitespace normalization |
| Numeric integrity | Infinities, arithmetic overflow and numeric exponent overflow could crash or disappear as missing data | Validation rejects these cases; model features outside representable float32 range are rejected without training |
| Quality reporting | Sensor tokens coerced to missing during analysis could disappear from the quality count | Missingness includes empty cells and non-numeric mapped sensor cells, while preserving literal IDs; UI explains the scope and overlapping counters |
| Alert ownership | Equipment/sensor pairs containing `\|` could share status keys | Opaque JSON tuple keys uniquely encode both values; resolving one pair leaves others unchanged |
| Evidence timing/charts | Asset-wide time could postdate the sensor evidence; downsampling exceeded200 or omitted latest point; chart showed only the upper threshold | Alert time uses the sensor's latest valid reading; at most200 chart samples include endpoints; upper/lower critical lines shown |
| Work orders | Empty title/unknown asset/blank status/invalid date accepted; multi-field writes could partially commit | Validated fields and references; one scoped SQL update makes each edit atomic |
| Model preparation | Test-period values influenced training imputation; generated names overwrote uploaded sensors | Training-only medians with zero fallback; feature construction preserves originals and chooses unique derived names |
| Browser data loading | Equipment fetch errors hidden on Overview; late responses could display the wrong machine | Both errors surfaced; request-generation checks discard stale responses |
| Status presentation | Unscored machines absent from health summary; sensor selection exposed only visually | All four status counts shown; sensor buttons expose `aria-pressed` |
| Regression execution | Browser tests could reuse unrelated servers; existing upload helper raced processing completion | Dedicated servers/temporary DB, retained failure traces, explicit ready-state wait and optional interpreter setting |

These changes do not calibrate the statistical thresholds, redefine failure episodes or make health a failure probability. Unknown labels are rejected rather than interpreted under an invented business definition. The original no-label model path remains available by leaving the failure role unmapped.

## Validation

- Initially33 new backend regression cases all failed against unchanged application code, establishing the initial defect reproductions.
- Review added seven further backend cases for numeric-ID inference, missing/invalid sensor accounting, exponent overflow, estimator numeric range and equivalent numeric duplicates. The final suite is57 passing cases:17 existing and40 new.
- Browser tests first reproduced five UI defects; the sixth new case covers maintenance save/completion. The first full run also exposed a timing flaw in the old upload helper; it now waits for Overview after processing.
- Final local Chromium run:13 passing cases, comprising seven existing and six new tests.
- Vite production build passed. Local runtime: Python3.10.11, pandas2.3.3, NumPy2.2.6, scikit-learn1.7.2, FastAPI0.115.0, pytest9.1.1; Node24.18.0 and locked frontend dependencies.
- One existing Starlette/AnyIO deprecation warning remains in the local backend runtime. Tests do not suppress it.
- Independent read-only code review identified the numeric-ID and quality/overflow edge cases; regression tests cover those corrections.

The inactive [GitHub Actions template](qa-workflow.example.yml) is prepared to run pytest, Vite build and Chromium tests on pull requests and pushes to main. The setup uses the maintained [checkout](https://github.com/actions/checkout), [Python](https://github.com/actions/setup-python) and [Node](https://github.com/actions/setup-node) actions. GitHub rejected publication as an active workflow because the available OAuth login lacks the `workflow` scope, so it is delivered as a template under `docs/`. Activation requires copying it to `.github/workflows/qa.yml` using an account with that permission. No completed GitHub Actions run is claimed.

## Remaining requirements and limitations

- Define canonical equipment IDs beyond text preservation, same-equipment/time conflicts, sensor units/physical ranges, timestamp timezone and stale-data policy. No new plant-maintenance policy was invented.
- Confirm that first60% of readings represent a valid healthy baseline, ten readings are sufficient, and symmetric1.5/3 sigma thresholds fit each machine/sensor. The displayed risk/health transformation remains uncalibrated.
- Agree failure episode semantics and provide labeled prospective holdout data, row-level prediction capture and metric acceptance targets. Current failure totals count flagged rows; the fitted estimator/predictions are not retained.
- Alert resolution, recommendation creation and work-order completion remain independent. Order deduplication and transition policy require an explicit product decision.
- Anonymous session tokens, in-memory datasets, missing authentication/TTL, restart recovery and multiple-worker consistency remain documented prototype limitations. Cross-resource replacement/clear operations are not a new global transaction. Load/race/fault-injection testing remains outstanding.
- Genuine legacy XLS, multi-sheet/formula/locale Excel, broad accessibility/screen-reader and cross-browser coverage remain unvalidated. XLSX text-identity preservation is covered. Legacy XLS needs the optional `xlrd` engine.
- No SKU, live telemetry/ERP, RUL, cost or drift engine exists. Adding those requires data contracts and implementation rather than tests for invented values.
- No production deployment or merge was performed as part of the local fixes. Python dependencies retain existing minimum-version requirements; there is no new lockfile or claim of exhaustive production validation.

The original discovery report remains a historical record of the supplied archive; these notes describe the subsequent fixes and their measured verification.
