# Sensor API

A RESTful Flask API that serves IoT-style sensor readings (temperature and humidity from five devices). The code lives on GitHub and is deployed to Render. A client script pulls the data into pandas, which makes the API a data source for big-data analysis.

```
Client (script, notebook, Spark)  --HTTP/JSON-->  Flask API (Render)  -->  SQLAlchemy  -->  SQLite / Postgres
                                                        ^
                                  GitHub push --webhook-+  (auto-deploy)
```

## Project layout

```
app/
  __init__.py          app factory, registers blueprints, error handlers
  config.py            config from environment variables
  extensions.py        db, cache, cors
  models.py            Device, Reading
  seed.py              synthetic data generator (20,000 readings by default)
  blueprints/
    health.py          GET /, GET /health
    devices.py         device resources
    readings.py        paginated list, single read, create
    stats.py           cached aggregates
client/fetch_all.py    paginated ingestion into pandas / Parquet
client/sources.py      step 1: load data from the API, a CSV, or a URL
client/analyze.py      step 2: averages, patterns, trend, anomalies, correlation
client/forecast.py     step 3: machine learning forecast, tested against baselines
tests/                 pytest suites (API and analysis)
wsgi.py                gunicorn entry point
render.yaml            Render deployment config
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check (used by Render) |
| GET | `/api/v1/devices` | List devices |
| GET | `/api/v1/devices/<id>` | One device |
| GET | `/api/v1/readings?device_id=&limit=&offset=` | Paginated readings (default 100, max 1000 per page) |
| GET | `/api/v1/readings/<id>` | One reading |
| POST | `/api/v1/readings` | Add a reading `{"device_id","temperature","humidity"}` |
| GET | `/api/v1/stats/summary?device_id=` | Count, avg/min/max temperature, avg humidity (cached 30 s) |

Paginated responses include metadata for the consumer:

```json
{"data": [...], "meta": {"total": 20000, "limit": 100, "offset": 0, "next_offset": 100,
                         "units": {"temperature": "C", "humidity": "%"}}}
```

## Units

| Field | Unit |
|---|---|
| `temperature` | degrees Celsius (C) |
| `humidity` | relative humidity, percent (valid range 0 to 100) |

The units are returned in every response (`meta.units` on lists, and `units` on single readings, `POST` responses, stats, and `GET /`), so consumers never have to guess. They are defined once as `UNITS` in `app/models.py`. Field names are unchanged, so existing clients keep working.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-analysis.txt   # server + client analysis/ML (the server alone needs only requirements.txt)
python wsgi.py                      # dev server on http://127.0.0.1:5000
# or, like production:
gunicorn wsgi:app --preload --workers 2
pytest                              # run the tests
python client/fetch_all.py http://127.0.0.1:5000 --out readings.parquet
```

## Analyze data (fetch, then analyze)

Analysis is two steps. **Step 1** loads data from a source you choose into pandas (`client/sources.py`). **Step 2** analyzes it (`client/analyze.py`).

```bash
# This project's API (local or deployed)
python client/analyze.py --api https://sensor-api-wrmk.onrender.com

# Your own CSV file: say which columns to use
python client/analyze.py --csv mydata.csv --value price --time date --group city --other volume

# A CSV or JSON file on the web
python client/analyze.py --url https://example.com/data.csv --value sales
```

| Option | Meaning | Default |
|---|---|---|
| `--api` / `--csv` / `--url` | Where to load data from (pick one) | required |
| `--value` | Numeric column to analyze | `temperature` |
| `--time` | Timestamp column (enables daily pattern and trend) | `ts` |
| `--group` | Category column (summary per group) | `device_id` |
| `--other` | Second numeric column to correlate with `--value` | `humidity` |

If a column doesn't exist, that analysis is skipped. If `--value` doesn't exist, the script lists the available columns.

**What it reports**

| Analysis | How |
|---|---|
| Averages | count, mean, median, std, min, max, overall or per group |
| Daily pattern | mean by hour of day. A pattern is reported if hour of day explains more than 5% of the variance. |
| Trend | linear slope per day, with the correlation `r` |
| Anomalies | rows more than 3 standard deviations from the mean |
| Correlation | Pearson `r` between `--value` and `--other` |

**Reading the results on the sample data.** The API's 20,000 readings are generated to behave like real sensors (see below), so the analysis finds a daily cycle (hour of day explains about 70% of the temperature variance, warmest around 20:00 UTC), humidity that falls as temperature rises (r of about -0.84), and temperatures that differ by location (Aspen is coldest, Pueblo warmest). On pure random noise, the same script correctly reports no pattern.

### Seeded data

`app/seed.py` generates temperature as a location baseline + a daily cycle (warmest about 3 pm local time) + slowly drifting weather shared by all devices + measurement noise. Humidity falls as temperature rises. Timestamps are UTC. The row count, devices, and endpoints are unchanged (20,000 readings, 5 devices).

## Forecast (machine learning)

`client/forecast.py` predicts the next hour of a value and, more importantly, **tests whether the models really help**.

```bash
python client/forecast.py --api https://sensor-api-wrmk.onrender.com
python client/forecast.py --api http://127.0.0.1:5000 --where device_id=1 --steps 12
python client/forecast.py --csv mydata.csv --value price --time date
```

| Option | Meaning | Default |
|---|---|---|
| `--api` / `--csv` / `--url` | Where to load data from (pick one) | required |
| `--value` | Numeric column to forecast | `temperature` |
| `--time` | Timestamp column | `ts` |
| `--where COL=VALUE` | Keep only rows where a column equals a value, e.g. one device | all rows |
| `--steps` | Hours to forecast | `24` |

**Method.** The data is averaged to one value per hour. Features are the value 1, 2, 3, and 24 hours earlier, plus the hour of day (as sine and cosine). Two models are trained, Ridge regression and Gradient boosting, on the first 80% of the timeline and scored on the last 20%, which they never saw (a time-ordered split, never shuffled). Their error (MAE, RMSE) is compared with three baselines: the training mean, "same as the last hour," and "same hour yesterday." The script says plainly when a model fails to beat the best baseline. The best model is then refit on all the data and forecasts the next `--steps` hours.

**Example result on the sample data** (local run, test period of 63 hours):

| Method | MAE |
|---|---|
| Ridge regression | 0.485 |
| Gradient boosting | 0.733 |
| Baseline: same as last hour | 1.222 |
| Baseline: same hour yesterday | 1.736 |
| Baseline: training mean | 4.682 |

Ridge is 60% better than the best baseline. Because the sample data is synthetic and built from a smooth daily cycle, this shows that the pipeline works and is evaluated fairly, not how well it would predict real weather. Exact numbers vary slightly between runs because the seeded timestamps start when the app starts. At least 72 hourly values are needed.

Add a new source by writing a `load_*` function in `client/sources.py` that returns a DataFrame.

## Deploy to Render

1. Push this folder to a GitHub repo.
2. In Render: **New > Blueprint** (reads `render.yaml`) or **New > Web Service** with:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn wsgi:app --preload --workers 2 --timeout 60`
3. Every push to the connected branch redeploys automatically.
4. For persistent data, add a Render Postgres database and set `DATABASE_URL`. Without it, the SQLite file is wiped on each restart (ephemeral filesystem), and the app re-seeds itself.

## How the design maps to the scaling concepts

| Concept | Where it shows up in the code |
|---|---|
| **Statelessness / horizontal scaling** | No session state. All data is in the database, so any worker or instance can serve any request (`--workers 2`, more instances on paid plans). |
| **Pagination** | `readings.py` caps `limit` at 1000 and returns `next_offset`, so a client reads 20,000 rows in 20 small requests instead of one huge response. |
| **Caching** | `stats.py` caches aggregate queries with Flask-Caching. Swap `SimpleCache` for Redis to share the cache across instances. |
| **Modularity** | One blueprint per resource, with an app factory and separate config, models, and seed modules. |
| **Loose coupling** | Clients depend only on the URL and JSON contract. Switching SQLite to Postgres is one environment variable (`DATABASE_URL`) and needs no client changes. |
| **Versioning** | Routes sit under `/api/v1/`, so a `/api/v2/` can ship without breaking existing consumers. |
| **Independent consumers** | `client/fetch_all.py` is a separate component. A Spark job or dashboard could use the same endpoints. |

## Known limitations

- **Cold starts:** Render's free tier sleeps after about 15 minutes idle. The first request takes 30 to 60 seconds, so the client uses a 90 s timeout.
- **Ephemeral storage:** SQLite data is lost on restart. Use Postgres for real persistence.
- **Offset pagination** gets slower on very deep pages. Keyset pagination (`WHERE id > last_id`) scales better.
- **Synchronous workers:** heavy concurrency needs more workers or a task queue for long jobs.
- **JSON for bulk data** is inefficient. At larger volumes, export to Parquet in object storage and read it directly with Spark.
- **No authentication:** add API keys or JWT before exposing write endpoints publicly.
- **Cache invalidation:** `POST /readings` does not clear the stats cache, so stats can be up to 30 s stale.
