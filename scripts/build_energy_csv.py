#!/usr/bin/env python3
"""Build data/energy_daily.csv for the calorie dashboard.

spent = InBody BMR (constant, measured) + Garmin active calories (steps + workouts)
        + TEF (thermic effect of food, 10% of eaten kcal; of plan kcal if eaten is not logged yet)
plan  = intake plan by weekday from the training guide
eaten = from data/nutrition.csv (date,kcal) when present, else blank
"""
import csv
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
BMR = 1245
TEF_SHARE = 0.10
PLAN = {0: 1750, 1: 1650, 2: 1750, 3: 1750, 4: 1650, 5: 1750, 6: 1650}  # Mon..Sun

eaten = {}
nut = DATA / "nutrition.csv"
if nut.exists():
    with nut.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("kcal", "").strip():
                eaten[r["date"]] = r["kcal"].strip()

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
        base = float(eaten[d]) if d in eaten else PLAN[wd]
        tef = round(base * TEF_SHARE)
        rows.append({"date": d, "spent": BMR + active + tef, "active": active, "tef": tef,
                     "garmin_total": total, "plan": PLAN[wd], "eaten": eaten.get(d, "")})

with (DATA / "energy_daily.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["date", "spent", "active", "tef", "garmin_total", "plan", "eaten"])
    w.writeheader()
    w.writerows(sorted(rows, key=lambda x: x["date"]))
print(len(rows), "rows")
