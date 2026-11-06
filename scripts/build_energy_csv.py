#!/usr/bin/env python3
"""Build data/energy_daily.csv for the calorie dashboard.

spent = InBody BMR (constant, measured) + Garmin active calories (steps + workouts)
        + TEF (thermic effect of food, 10% of eaten kcal; of plan kcal if eaten is not logged yet)
active is corrected: Garmin active calories are multiplied by K (default 0.85, studies show 15-25%
overestimation; recalibrate from the weight trend). Cycling sessions with avgPower use mechanical work
(kJ ~ kcal at ~24% efficiency, minus the resting part) instead of Garmin calories, without K.
plan  = intake plan by weekday from the training guide
eaten = from data/nutrition.csv (date,kcal) when present, else blank
"""
import csv
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
BMR = 1245
K = 0.85  # correction of Garmin active calories; recalibrate after 4 weeks from weight trend
TEF_SHARE = 0.10
PLAN = {0: 1750, 1: 1650, 2: 1650, 3: 1750, 4: 1650, 5: 1750, 6: 1650}  # Mon..Sun

eaten = {}
nut = DATA / "nutrition.csv"
if nut.exists():
    with nut.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("kcal", "").strip():
                eaten[r["date"]] = r["kcal"].strip()

# cycling sessions with power: per date -> (garmin net kcal, power-based net kcal)
cyc = {}
act_path = DATA / "activities.csv"
if act_path.exists():
    with act_path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = r.get("activityType.typeKey", "")
            if "cycling" not in key and "virtual_ride" not in key:
                continue
            try:
                power = float(r["avgPower"])
                secs = float(r.get("movingDuration") or r["duration"])
                cal = float(r["calories"])
                bmr = float(r.get("bmrCalories") or 0)
            except (KeyError, ValueError):
                continue
            kj = power * secs / 1000.0
            d = r["startTimeLocal"][:10]
            g, p = cyc.get(d, (0.0, 0.0))
            cyc[d] = (g + max(cal - bmr, 0), p + max(kj - bmr, 0))

rows = []
with (DATA / "daily_summaries.csv").open(newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        d = r["date"]
        try:
            active = round(float(r["calories.burnedActive"]))
            total = round(float(r["calories.burnedTotal"]))
        except (KeyError, ValueError):
            continue
        wd = date.fromisoformat(d).weekday()
        g, p = cyc.get(d, (0.0, 0.0))
        active_adj = round(K * max(active - g, 0) + p)
        base = float(eaten[d]) if d in eaten else PLAN[wd]
        tef = round(base * TEF_SHARE)
        rows.append({"date": d, "spent": BMR + active_adj + tef, "active": active, "active_adj": active_adj, "tef": tef,
                     "garmin_total": total, "plan": PLAN[wd], "eaten": eaten.get(d, "")})

with (DATA / "energy_daily.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["date", "spent", "active", "active_adj", "tef", "garmin_total", "plan", "eaten"])
    w.writeheader()
    w.writerows(sorted(rows, key=lambda x: x["date"]))
print(len(rows), "rows")
