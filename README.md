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
tests/test_api.py      pytest suite
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
{"data": [...], "meta": {"total": 20000, "limit": 100, "offset": 0, "next_offset": 100}}
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python wsgi.py                      # dev server on http://127.0.0.1:5000
# or, like production:
gunicorn wsgi:app --preload --workers 2
pytest                              # run the tests
python client/fetch_all.py http://127.0.0.1:5000 --out readings.parquet
```

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
