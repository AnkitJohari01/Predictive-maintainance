"""Dataset profiling, validation and analytics. Pure functions, no web code."""
import csv, io, re, warnings
import numpy as np
import pandas as pd

ALLOWED = (".csv", ".xlsx", ".xls")
ID_RE, FAIL_RE, TIME_RE = r"(^|_)(id|machine|asset|equip|unit)", r"fail|fault|label|target", r"time|date|stamp|^ts$"
BOOLS = {"0", "1", "0.0", "1.0", "true", "false"}
WATCH_Z, CRIT_Z, MIN_POINTS = 1.5, 3.0, 10


def ts_of(s):
    if pd.api.types.is_numeric_dtype(s):
        return pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, UTC]")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pd.to_datetime(s, errors="coerce", format="mixed", utc=True)


def numeric(s):
    # Extremely large values cannot represent usable equipment measurements.
    v = pd.to_numeric(s, errors="coerce")
    return v.where(np.isfinite(v) & (v.abs() <= 1e100))


def read_upload(name, raw):
    n = name.lower()
    if not n.endswith(ALLOWED):
        raise ValueError(f"'{name}' is not supported. Upload a .csv, .xlsx or .xls file.")
    try:
        if n.endswith(".csv"):
            headers = next(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
            df = pd.read_csv(io.BytesIO(raw))
        else:
            sheet = pd.read_excel(io.BytesIO(raw), header=None)
            headers = sheet.iloc[0].tolist() if not sheet.empty else []
            df = sheet.iloc[1:].reset_index(drop=True).infer_objects()
    except Exception as e:  # re-raised with a user-facing message, never swallowed
        raise ValueError(f"The file could not be read as a table: {e}") from e
    if df.empty or df.shape[1] < 3:
        raise ValueError("The file needs a header row, at least one data row and at least 3 columns.")
    headers = [str(c).strip() if pd.notna(c) else "" for c in headers]
    if not all(headers) or len(set(headers)) != len(headers):
        raise ValueError("Column headers must be non-empty and unique, including after trimming spaces.")
    df.columns = headers
    return df


def infer(df):
    cands = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c]) and df[c].notna().any()
             and ts_of(df[c].dropna().astype(str)).notna().mean() > .8]
    ts = next((c for c in cands if re.search(TIME_RE, c, re.I)), cands[0] if cands else None)
    idc = next((c for c in df.columns if c != ts and re.search(ID_RE, c, re.I)), None)
    fl = next((c for c in df.columns if c not in (ts, idc) and re.search(FAIL_RE, c, re.I)
               and set(df[c].dropna().astype(str).str.strip().str.lower()) <= BOOLS), None)
    sens = [c for c in df.columns if c not in (ts, idc, fl) and df[c].notna().any()
            and numeric(df[c]).notna().sum() >= .9 * df[c].notna().sum()]
    return {"timestamp": ts, "id": idc, "failure": fl, "sensors": sens}


def blockers(df, m):
    cols, e = set(df.columns), []
    if m.get("timestamp") not in cols: e.append("Pick a valid timestamp column.")
    if m.get("id") not in cols: e.append("Pick a valid equipment ID column.")
    if m.get("failure") and m["failure"] not in cols: e.append("The selected failure column does not exist.")
    sens = [c for c in m.get("sensors", []) if c in cols]
    if len(sens) != len(m.get("sensors", [])): e.append("One or more selected sensor columns do not exist.")
    if not sens: e.append("Select at least one numeric sensor column.")
    if e: return e
    if len(df) < 20: e.append(f"Only {len(df)} data rows found. At least 20 are needed to build a baseline.")
    if ts_of(df[m["timestamp"]]).isna().mean() > .3: e.append("More than 30% of timestamps cannot be read. Use dates or ISO timestamps; convert numeric epoch or Excel serial values first.")
    bad = [c for c in sens if numeric(df[c]).notna().sum() == 0]
    if bad: e.append(f"These sensor columns contain no finite usable numbers: {', '.join(bad)}.")
    roles = [r for r in (m["timestamp"], m["id"], m.get("failure"), *sens) if r]
    if len(set(roles)) != len(roles): e.append("A column cannot be used for two roles.")
    if m.get("failure"):
        labels = df[m["failure"]].astype("string").str.strip().str.lower()
        if not labels.isin(BOOLS).all():
            e.append("Failure flags must contain only 0/1 or true/false, with no missing values. Correct the labels or choose None.")
    if not e:
        d = clean(df, m)
        if len(d) < 20: e.append(f"Only {len(d)} usable unique rows remain after cleaning. At least 20 are needed.")
        if d[sens].notna().sum().sum() == 0: e.append("No sensor readings remain after cleaning.")
    return e


def quality(df, m):
    out = 0
    for c in m["sensors"]:
        v = numeric(df[c]).dropna(); s = v.std()
        if s and s > 0: out += int((((v - v.mean()) / s).abs() > 4).sum())
    miss = int(df.isna().sum().sum())
    d = clean(df, m)
    return {"rows": len(df), "usable_rows": len(d), "excluded_rows": len(df) - len(d),
            "invalid_sensor_values": sum(int((df[c].notna() & numeric(df[c]).isna()).sum()) for c in m["sensors"]),
            "missing": miss, "missing_pct": round(100 * miss / df.size, 2),
            "duplicates": int(df.duplicated().sum()), "bad_timestamps": int(ts_of(df[m["timestamp"]]).isna().sum()), "outliers": out}


def clean(df, m):
    d = df.drop_duplicates().copy(); ts = m["timestamp"]
    d[ts] = ts_of(d[ts])
    d[m["id"]] = d[m["id"]].astype("string").str.strip().replace("", pd.NA)
    d = d.dropna(subset=[ts, m["id"]])
    for c in m["sensors"]: d[c] = numeric(d[c])
    d = d.dropna(subset=m["sensors"], how="all")
    if m.get("failure"): d[m["failure"]] = d[m["failure"]].astype(str).str.strip().str.lower().isin(["1", "1.0", "true"]).astype(int)
    return d.sort_values(ts, kind="stable")


def status_of(z):
    return None if z is None else "critical" if abs(z) >= CRIT_Z else "watch" if abs(z) >= WATCH_Z else "healthy"


def analyse(df, m):
    ts, idc, fl = m["timestamp"], m["id"], m.get("failure")
    d = clean(df, m); assets, alerts = [], []
    for aid, g in d.groupby(idc):
        aid, sc = str(aid), {}
        for c in m["sensors"]:
            s = g[[ts, c]].dropna()
            if len(s) < MIN_POINTS: continue
            v = s[c].to_numpy(); base = v[: int(len(v) * .6)]
            mu = float(base.mean()); sd = float(max(base.std(), abs(mu) * .01, 1e-6))
            rec = float(v[-3:].mean()); z = (rec - mu) / sd
            indices = np.unique(np.linspace(0, len(s) - 1, min(200, len(s)), dtype=int))
            sc[c] = {"baseline": mu, "std": sd, "recent": rec, "z": z, "status": status_of(z),
                     "points": [{"t": t.isoformat(), "v": float(x)} for t, x in zip(s[ts].iloc[indices], v[indices])]}
            if abs(z) >= WATCH_Z:
                alerts.append({"key": f"{len(aid)}:{aid}{c}", "asset": aid, "sensor": c, "severity": status_of(z), "z": z, "recent": rec, "baseline": mu,
                               "threshold_z": CRIT_Z if abs(z) >= CRIT_Z else WATCH_Z, "data_timestamp": g[ts].max().strftime("%Y-%m-%d %H:%M UTC"),
                               "why": f"{c} averaged {rec:.2f} over the last 3 readings, {abs(z):.1f} standard deviations {'above' if z > 0 else 'below'} this machine's own baseline of {mu:.2f}.",
                               "action": f"Inspect {aid} ({c}) at the next maintenance window."})
        mz = max((abs(x["z"]) for x in sc.values()), default=None)
        assets.append({"id": aid, "records": len(g), "last": g[ts].max().strftime("%Y-%m-%d %H:%M UTC"), "sensors": sc, "max_z": mz or 0.0,
                       "worst": max(sc, key=lambda k: abs(sc[k]["z"])) if sc else None, "status": status_of(mz) or "unscored",
                       "risk": min(100, round((mz or 0) * 25)), "failures": int(g[fl].sum()) if fl else None})
    for a in assets: a["health"] = 100 - a["risk"] if a["status"] != "unscored" else None
    return {"assets": sorted(assets, key=lambda a: -a["max_z"]), "alerts": sorted(alerts, key=lambda a: -abs(a["z"])), "records": len(d)}, d


def recommendations(assets):
    out = []
    for a in (x for x in assets if x["status"] in ("critical", "watch")):
        s = a["sensors"][a["worst"]]
        out.append({"priority": len(out) + 1, "asset": a["id"], "status": a["status"], "sensor": a["worst"],
                    "action": f"Inspect {a['id']} for {a['worst']} {'rise' if s['z'] > 0 else 'drop'} at the next maintenance window.",
                    "evidence": f"Recent {s['recent']:.2f} vs baseline {s['baseline']:.2f} ({s['z']:+.1f} std)."})
    return out
