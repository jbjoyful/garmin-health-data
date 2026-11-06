# garmin-health-data

Private repository. A GitHub Actions workflow (`fetch-garmin`) pulls Garmin data once a day
through the official Garmin Personal API and stores it under `data/`.

- `data/raw/<command>/...json` raw responses
- `data/<name>.csv` flattened daily rows (merged by date)
- `data/cycle.csv` cycle day and phase per date (for interpreting trends)
- `data/runs.csv` log of every call (exit code, size, stderr)

Secret required: `GARMIN_PERSONAL_API_KEY` (Settings -> Secrets and variables -> Actions).
The key expires (set 365 days at creation); create a new one before that and replace the secret.
