"""Dataset profiling, validation and analytics. Pure functions, no web code."""
import io, re, warnings
import pandas as pd

ALLOWED = (".csv", ".xlsx", ".xls")
ID_RE, FAIL_RE, TIME_RE = r"(^|_)(id|machine|asset|equip|unit)", r"fail|fault|label|target", r"time|date|stamp|^ts$"
BOOLS = {"0", "1", "0.0", "1.0", "true", "false"}
WATCH_Z, CRIT_Z, MIN_POINTS = 1.5, 3.0, 10


def ts_of(s):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pd.to_datetime(s, errors="coerce")


def read_upload(name, raw):
    n = name.lower()
    if not n.endswith(ALLOWED):
        raise ValueError(f"'{name}' is not supported. Upload a .csv, .xlsx or .xls file.")
    try:
        df = pd.read_csv(io.BytesIO(raw)) if n.endswith(".csv") else pd.read_excel(io.BytesIO(raw))
    except Exception as e:  # re-raised with a user-facing message, never swallowed
        raise ValueError(f"The file could not be read as a table: {e}") from e
    if df.empty or df.shape[1] < 3:
        raise ValueError("The file needs a header row, at least one data row and at least 3 columns.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def infer(df):
    cands = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c]) and df[c].notna().any()
             and ts_of(df[c].dropna().astype(str)).notna().mean() > .8]
    ts = next((c for c in cands if re.search(TIME_RE, c, re.I)), cands[0] if cands else None)
    idc = next((c for c in df.columns if c != ts and re.search(ID_RE, c, re.I) and df[c].nunique() < len(df) / 3), None)
    fl = next((c for c in df.columns if c not in (ts, idc) and re.search(FAIL_RE, c, re.I)
               and set(df[c].dropna().astype(str).str.lower()) <= BOOLS), None)
    sens = [c for c in df.columns if c not in (ts, idc, fl) and df[c].notna().any()
            and pd.to_numeric(df[c], errors="coerce").notna().sum() >= .9 * df[c].notna().sum()]
    return {"timestamp": ts, "id": idc, "failure": fl, "sensors": sens}


def blockers(df, m):
    cols, e = set(df.columns), []
    if m.get("timestamp") not in cols: e.append("Pick a valid timestamp column.")
    if m.get("id") not in cols: e.append("Pick a valid equipment ID column.")
    if m.get("failure") and m["failure"] not in cols: e.append("The selected failure column does not exist.")
    sens = [c for c in m.get("sensors", []) if c in cols]
    if not sens: e.append("Select at least one numeric sensor column.")
    if e: return e
    if len(df) < 20: e.append(f"Only {len(df)} data rows found. At least 20 are needed to build a baseline.")
    if ts_of(df[m["timestamp"]]).isna().mean() > .3: e.append("More than 30% of timestamps cannot be read. Check the timestamp column.")
    bad = [c for c in sens if pd.to_numeric(df[c], errors="coerce").notna().sum() == 0]
    if bad: e.append(f"These sensor columns contain no numbers: {', '.join(bad)}.")
    roles = [r for r in (m["timestamp"], m["id"], m.get("failure"), *sens) if r]
    if len(set(roles)) != len(roles): e.append("A column cannot be used for two roles.")
    return e


def quality(df, m):
    out = 0
    for c in m["sensors"]:
        v = pd.to_numeric(df[c], errors="coerce").dropna(); s = v.std()
        if s and s > 0: out += int((((v - v.mean()) / s).abs() > 4).sum())
    miss = int(df.isna().sum().sum())
    return {"rows": len(df), "missing": miss, "missing_pct": round(100 * miss / df.size, 2),
            "duplicates": int(df.duplicated().sum()), "bad_timestamps": int(ts_of(df[m["timestamp"]]).isna().sum()), "outliers": out}


def clean(df, m):
    d = df.drop_duplicates().copy(); ts = m["timestamp"]
    d[ts] = ts_of(d[ts]); d = d.dropna(subset=[ts, m["id"]])
    for c in m["sensors"]: d[c] = pd.to_numeric(d[c], errors="coerce")
    if m.get("failure"): d[m["failure"]] = d[m["failure"]].astype(str).str.lower().isin(["1", "1.0", "true"]).astype(int)
    return d.sort_values(ts)


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
            rec = float(v[-3:].mean()); z = (rec - mu) / sd; step = max(1, len(s) // 200)
            sc[c] = {"baseline": mu, "std": sd, "recent": rec, "z": z, "status": status_of(z),
                     "points": [{"t": t.strftime("%Y-%m-%d %H:%M"), "v": float(x)} for t, x in zip(s[ts].iloc[::step], v[::step])]}
            if abs(z) >= WATCH_Z:
                alerts.append({"key": f"{aid}|{c}", "asset": aid, "sensor": c, "severity": status_of(z), "z": z, "recent": rec, "baseline": mu,
                               "threshold_z": CRIT_Z if abs(z) >= CRIT_Z else WATCH_Z, "data_timestamp": g[ts].max().strftime("%Y-%m-%d %H:%M"),
                               "why": f"{c} averaged {rec:.2f} over the last 3 readings, {abs(z):.1f} standard deviations {'above' if z > 0 else 'below'} this machine's own baseline of {mu:.2f}.",
                               "action": f"Inspect {aid} ({c}) at the next maintenance window."})
        mz = max((abs(x["z"]) for x in sc.values()), default=None)
        assets.append({"id": aid, "records": len(g), "last": g[ts].max().strftime("%Y-%m-%d %H:%M"), "sensors": sc, "max_z": mz or 0.0,
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
