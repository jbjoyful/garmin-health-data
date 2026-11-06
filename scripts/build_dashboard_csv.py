#!/usr/bin/env python3
"""Build compact CSVs for the health dashboard artifact.

data/dash_daily.csv      one row per day (steps, heart, stress, body battery, sleep, HRV, weight, energy)
data/dash_activities.csv one row per workout (type, minutes, kcal, HR, power, net kcal used in energy calc)
Run after build_energy_csv.py.
"""
import csv
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
BMR = 1245  # InBody
K = 0.85  # same correction as build_energy_csv.py


def rows(name):
    p = DATA / name
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(x, scale=1.0, nd=2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return ""
    v = v * scale
    return round(v, nd) if nd else round(v)


daily = {}
for r in rows("daily_summaries.csv"):
    d = r["date"]
    daily[d] = {
        "date": d,
        "steps": num(r.get("movement.steps.value"), nd=0),
        "step_goal": num(r.get("movement.steps.goal"), nd=0),
        "resting_hr": num(r.get("heartRate.restingValue"), nd=0),
        "stress_avg": num(r.get("stress.avgLevel"), nd=0),
        "bb_max": num(r.get("bodyBattery.maxValue"), nd=0),
        "bb_min": num(r.get("bodyBattery.minValue"), nd=0),
        "bb_charged": num(r.get("bodyBattery.chargedValue"), nd=0),
        "bb_drained": num(r.get("bodyBattery.drainedValue"), nd=0),
        "intensity_min": (num(r.get("intensityMinutes.moderate"), nd=0) or 0) + 2 * (num(r.get("intensityMinutes.vigorous"), nd=0) or 0),
        "active_kcal": num(r.get("calories.burnedActive"), nd=0),
    }

for r in rows("energy_daily.csv"):
    x = daily.setdefault(r["date"], {"date": r["date"]})
    for k in ("spent", "active_adj", "tef", "plan", "eaten"):
        x[k] = r.get(k, "")
    x["basal"] = BMR

for r in rows("sleep_summaries.csv"):
    x = daily.setdefault(r["date"], {"date": r["date"]})
    x["sleep_h"] = num(r.get("sleepTimeSeconds"), 1 / 3600)
    x["deep_h"] = num(r.get("deepSleepSeconds"), 1 / 3600)
    x["light_h"] = num(r.get("lightSleepSeconds"), 1 / 3600)
    x["rem_h"] = num(r.get("remSleepSeconds"), 1 / 3600)
    x["awake_h"] = num(r.get("awakeSleepSeconds"), 1 / 3600)
    x["sleep_score"] = num(r.get("sleepScores.overall.value"), nd=0)
    x["sleep_hr"] = num(r.get("avgHeartRate"), nd=0)

for r in rows("hrv_summaries.csv"):
    x = daily.setdefault(r["date"], {"date": r["date"]})
    x["hrv"] = num(r.get("lastNightAvg"), nd=0)
    x["hrv_week"] = num(r.get("weeklyAvg"), nd=0)
    x["hrv_status"] = r.get("status", "")
    x["hrv_low"] = num(r.get("baseline.balancedLow"), nd=0)
    x["hrv_high"] = num(r.get("baseline.balancedUpper"), nd=0)

# weight: grams or kg, whichever column Garmin gives
wrows = rows("weight_measurements.csv")
if wrows:
    wcols = [c for c in wrows[0] if c.lower().endswith("weight") and "avg" not in c.lower()]
    for r in wrows:
        for c in wcols:
            v = num(r.get(c))
            if v != "":
                x = daily.setdefault(r["date"], {"date": r["date"]})
                x["weight"] = round(v / 1000 if v > 300 else v, 1)
                break

fields = ["date", "steps", "step_goal", "resting_hr", "stress_avg", "bb_max", "bb_min", "bb_charged", "bb_drained",
          "intensity_min", "active_kcal", "basal", "active_adj", "tef", "spent", "plan", "eaten",
          "sleep_h", "deep_h", "light_h", "rem_h", "awake_h", "sleep_score", "sleep_hr",
          "hrv", "hrv_week", "hrv_status", "hrv_low", "hrv_high", "weight"]
with (DATA / "dash_daily.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields, restval="")
    w.writeheader()
    for d in sorted(daily):
        w.writerow({k: daily[d].get(k, "") for k in fields})

# activities
TYPE = {"strength_training": "Силовая", "indoor_cycling": "Велотренажёр", "virtual_ride": "Виртуальная поездка",
        "cycling": "Велосипед", "tennis_v2": "Теннис", "tennis": "Теннис", "breathwork": "Дыхание",
        "walking": "Ходьба", "running": "Бег", "yoga": "Йога", "hiit": "HIIT"}
out = []
for r in rows("activities.csv"):
    key = r.get("activityType.typeKey", "")
    cal = num(r.get("calories"))
    if cal == "" or cal == 0:
        continue
    bmr = num(r.get("bmrCalories")) or 0
    secs = num(r.get("movingDuration")) or num(r.get("duration")) or 0
    power = num(r.get("avgPower"))
    kj = round(power * secs / 1000, 0) if power != "" else ""
    if kj != "" and ("cycling" in key or "virtual_ride" in key):
        net = max(kj - bmr, 0)
    else:
        net = K * max(cal - bmr, 0)
    out.append({
        "date": r["startTimeLocal"][:10], "start": r["startTimeLocal"][11:16], "type": TYPE.get(key, key),
        "duration_min": round((num(r.get("duration")) or 0) / 60), "kcal": round(cal), "net_kcal": round(net),
        "avg_hr": (lambda v: v if v != "" and v >= 40 else "")(num(r.get("averageHR"), nd=0)), "max_hr": num(r.get("maxHR"), nd=0),
        "avg_power": num(power, nd=0) if power != "" else "", "kj": kj,
        "load": num(r.get("activityTrainingLoad"), nd=0), "aerobic_te": num(r.get("aerobicTrainingEffect"), nd=1),
    })
out.sort(key=lambda x: (x["date"], x["start"]))
af = ["date", "start", "type", "duration_min", "kcal", "net_kcal", "avg_hr", "max_hr", "avg_power", "kj", "load", "aerobic_te"]
with (DATA / "dash_activities.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=af, restval="")
    w.writeheader()
    w.writerows(out)
print(len(daily), "days,", len(out), "activities")
