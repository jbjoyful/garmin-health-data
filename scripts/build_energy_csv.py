#!/usr/bin/env python3
"""Build data/energy_daily.csv for the calorie dashboard.

spent = InBody BMR (constant, measured) + Garmin active calories (steps + workouts)
plan  = intake plan by weekday from the training guide
eaten = from data/nutrition.csv (date,kcal) when present, else blank
"""
import csv
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
BMR = 1245
PLAN = {0: 1900, 1: 1700, 2: 1900, 3: 1800, 4: 1700, 5: 1800, 6: 1900}  # Mon..Sun

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
        rows.append({"date": d, "spent": BMR + active, "active": active, "garmin_total": total,
                     "plan": PLAN[wd], "eaten": eaten.get(d, "")})

with (DATA / "energy_daily.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["date", "spent", "active", "garmin_total", "plan", "eaten"])
    w.writeheader()
    w.writerows(sorted(rows, key=lambda x: x["date"]))
print(len(rows), "rows")
