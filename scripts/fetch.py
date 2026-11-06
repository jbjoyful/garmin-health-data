#!/usr/bin/env python3
"""Daily Garmin data fetch via the official Garmin Personal API client (gc-personal CLI).

Saves raw JSON for every endpoint and merges flattened daily rows into CSV files.
Exit code is non-zero if a critical endpoint fails, so the GitHub Actions run is
marked failed and GitHub notifies the owner.
"""
import argparse
import csv
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
TZ = ZoneInfo("Europe/Amsterdam")

# command -> (extra args builder kind, critical)
RANGE_CMDS = {
    "daily-summaries": True,
    "sleep-summaries": True,
    "hrv-summaries": False,
    "body-battery": False,
    "stress": False,
    "steps": False,
    "weight-measurements": False,
    "wellness-activity-summaries": False,
}
DAY_CMDS = {"heart-rate": False, "food-logs": False}
# commands whose output is flattened into data/<name>.csv (one row per date)
CSV_CMDS = ["daily-summaries", "sleep-summaries", "hrv-summaries", "body-battery",
            "stress", "steps", "weight-measurements", "wellness-activity-summaries"]


def run(args):
    proc = subprocess.run(["gc-personal", "--quiet", "--no-color", *args],
                          capture_output=True, text=True, timeout=180)
    return proc.returncode, proc.stdout, proc.stderr


def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        if all(not isinstance(i, (dict, list)) for i in obj):
            out[prefix.rstrip(".")] = json.dumps(obj)
        else:
            out[prefix.rstrip(".")] = json.dumps(obj)[:2000]
    else:
        out[prefix.rstrip(".")] = obj
    return out


def find_rows(payload):
    """Return list of dicts (one per date) from a payload that is a list or has a list inside."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        return [payload]
    return []


def row_date(row):
    for k in ("calendarDate", "date", "summaryDate", "startDate", "measurementDate", "calendar_date"):
        v = row.get(k)
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    return None


def merge_csv(name, rows):
    path = DATA / f"{name}.csv"
    existing = {}
    cols = ["date"]
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            cols = list(reader.fieldnames or ["date"])
            for r in reader:
                existing[r["date"]] = r
    for row in rows:
        d = row_date(row)
        if not d:
            continue
        flat = flatten(row)
        flat["date"] = d
        for k in flat:
            if k not in cols:
                cols.append(k)
        existing[d] = {k: ("" if v is None else v) for k, v in flat.items()}
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for d in sorted(existing):
            w.writerow(existing[d])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="how many days back to (re)fetch, ending yesterday")
    ap.add_argument("--weight-only", action="store_true", help="fetch only weigh-ins, through today (midday run)")
    args = ap.parse_args()

    end = datetime.now(TZ).date() - (timedelta(days=0) if args.weight_only else timedelta(days=1))
    start = end - timedelta(days=args.days - 1)
    s, e = start.isoformat(), end.isoformat()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    RAW.mkdir(parents=True, exist_ok=True)
    log_rows, failed_critical = [], []

    def record(cmd, key, rc, out, err, critical):
        folder = RAW / cmd
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{key}.json").write_text(out if out.strip() else "", encoding="utf-8")
        log_rows.append([stamp, cmd, key, rc, len(out), err.strip().replace("\n", " ")[:300]])
        if rc != 0 and critical:
            failed_critical.append(cmd)

    if args.weight_only:
        start = end - timedelta(days=6)
        s = start.isoformat()
        rc, out, err = run(["weight-measurements", "--start-date", s, "--end-date", e])
        record("weight-measurements", f"{s}_{e}", rc, out, err, True)
        if rc == 0:
            try:
                merge_csv("weight_measurements", find_rows(json.loads(out)))
            except Exception as ex:
                log_rows.append([stamp, "weight-measurements", "csv-merge", 1, 0, repr(ex)[:300]])
        logp = DATA / "runs.csv"
        with logp.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(log_rows)
        if failed_critical:
            print("weight fetch failed", file=sys.stderr)
            sys.exit(1)
        print(f"OK weight {s}..{e}")
        return

    for cmd, critical in RANGE_CMDS.items():
        rc, out, err = run([cmd, "--start-date", s, "--end-date", e])
        record(cmd, f"{s}_{e}", rc, out, err, critical)
        if rc == 0 and cmd in CSV_CMDS:
            try:
                merge_csv(cmd.replace("-", "_"), find_rows(json.loads(out)))
            except Exception as ex:  # keep going, raw is saved
                log_rows.append([stamp, cmd, "csv-merge", 1, 0, repr(ex)[:300]])

    rc, out, err = run(["activities", "--start", "0", "--limit", "100", "--start-date", s, "--end-date", e])
    record("activities", f"{s}_{e}", rc, out, err, True)
    if rc == 0:
        try:
            rows = find_rows(json.loads(out))
            for r in rows:
                r.setdefault("date", str(r.get("startTimeLocal", r.get("startTimeGMT", "")))[:10])
            # one row per activity -> separate file keyed by activity id
            path = DATA / "activities.csv"
            existing, cols = {}, ["activityId"]
            if path.exists():
                with path.open(newline="", encoding="utf-8") as f:
                    rd = csv.DictReader(f)
                    cols = list(rd.fieldnames or cols)
                    existing = {r["activityId"]: r for r in rd}
            for r in rows:
                flat = flatten(r)
                aid = str(flat.get("activityId", ""))
                if not aid:
                    continue
                for k in flat:
                    if k not in cols:
                        cols.append(k)
                existing[aid] = {k: ("" if v is None else v) for k, v in flat.items()}
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                for aid in existing:
                    w.writerow(existing[aid])
        except Exception as ex:
            log_rows.append([stamp, "activities", "csv-merge", 1, 0, repr(ex)[:300]])

    d = start
    while d <= end:
        for cmd, critical in DAY_CMDS.items():
            rc, out, err = run([cmd, "--date", d.isoformat()])
            record(cmd, d.isoformat(), rc, out, err, critical)
        d += timedelta(days=1)

    # cycle phase (used only for interpreting weight, energy and recovery trends)
    cycle_rows = []
    d = start
    while d <= end:
        rc, out, err = run(["menstrual-cycle-day-view", "--date", d.isoformat()])
        record("menstrual-cycle-day-view", d.isoformat(), rc, out, err, False)
        if rc == 0:
            try:
                ds = (json.loads(out) or {}).get("daySummary") or {}
                if ds:
                    row = {"date": d.isoformat()}
                    row.update(ds)
                    cycle_rows.append(row)
            except Exception as ex:
                log_rows.append([stamp, "menstrual-cycle-day-view", "parse", 1, 0, repr(ex)[:300]])
        d += timedelta(days=1)
    if cycle_rows:
        merge_csv("cycle", cycle_rows)

    logp = DATA / "runs.csv"
    new = not logp.exists()
    with logp.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["run_utc", "command", "key", "exit_code", "bytes", "stderr"])
        w.writerows(log_rows)

    if failed_critical:
        print("CRITICAL endpoints failed:", ", ".join(sorted(set(failed_critical))), file=sys.stderr)
        sys.exit(1)
    print(f"OK {s}..{e}")


if __name__ == "__main__":
    main()
