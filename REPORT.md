# Advantages of a RESTful Flask Approach When Scaling: The Sensor API Project

## 1. Introduction

This project is a RESTful API built with Flask that serves IoT-style sensor readings (temperature and humidity) from five devices in Colorado (Boulder, Denver, Fort Collins, Aspen, Pueblo). The code is stored on GitHub and deployed on Render, which replaced Heroku because Heroku charged from the start to run the API. A client script pulls data from the API into pandas, so the API acts as a data source for analysis. This report explains how the RESTful approach helps the system scale to larger data volumes and more users, using the project's own design as evidence. It covers scalability, modularity, and loose coupling, and it also covers the limits of the approach.

## 2. System Overview

```
Client (script, notebook, Spark)  --HTTP/JSON-->  Flask API (Render)  -->  SQLAlchemy  -->  SQLite / Postgres
                                                        ^
                                  GitHub push --webhook-+  (auto-deploy)
```

**Components**

| Component | Role |
|---|---|
| Flask app (`app/`) | Handles HTTP requests, validation, and serialization |
| Database (SQLite locally, Postgres via `DATABASE_URL`) | Stores devices and readings |
| gunicorn | Production server running 2 workers |
| GitHub | Source of truth. A push triggers a deployment. |
| Render | Builds and hosts the API (`render.yaml`) |
| Client (`client/fetch_all.py`) | Pulls all readings into pandas or Parquet |

**Data.** The API generates 20,000 synthetic readings at startup (4,000 per device, one per minute), configurable with `SEED_READINGS`.

**Units.** `temperature` is in degrees Celsius and `humidity` is relative humidity in percent (0 to 100). Both are declared once as `UNITS` in `app/models.py` and returned in every response (`meta.units` on lists, `units` on single readings, writes, stats, and the index). The first deployed version did not state units, so a consumer could not tell whether temperatures were Celsius or Fahrenheit. Adding the units as separate metadata, without renaming fields, fixed this without breaking existing clients, which is the kind of backward-compatible change the `/api/v1` contract is meant to allow.

**Endpoints** (prefix `/api/v1`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check used by Render |
| GET | `/devices`, `/devices/<id>` | List devices, or fetch one |
| GET | `/readings?device_id=&limit=&offset=` | Paginated, filterable readings |
| GET | `/readings/<id>` | One reading |
| POST | `/readings` | Add a reading, with validation |
| GET | `/stats/summary?device_id=` | Count, average/min/max temperature, average humidity (cached) |

## 3. Scalability

**Statelessness enables horizontal scaling.** The API keeps no session state. Each request carries everything needed to answer it, and all data lives in the database. Any worker or instance can serve any request. The project already runs 2 gunicorn workers (`--workers 2`), and adding capacity means raising that number or running more instances behind Render's load balancer on a paid plan.

**Pagination bounds the cost of each request.** `GET /readings` returns 100 rows by default and never more than 1,000 (`MAX_PAGE_SIZE`). Each response includes metadata:

```json
{"data": [...], "meta": {"total": 20000, "limit": 100, "offset": 0, "next_offset": 100,
                         "units": {"temperature": "C", "humidity": "%"}}}
```

The client follows `next_offset` until it is `null`. Against the deployed service on Render, the client pulled all 20,000 rows in 20 requests of 1,000 rows each in 5.4 to 5.9 seconds (see Section 8). If the dataset grew to 20 million rows, the per-request cost would stay the same. Only the number of requests would grow, and a distributed job could split them across workers.

**Caching reduces repeated work.** `GET /stats/summary` runs aggregate queries (COUNT, AVG, MIN, MAX) over the whole table. Flask-Caching stores each result for 30 seconds, keyed by query string, so repeated dashboard refreshes do not reach the database. The cache is in memory (`SimpleCache`). Switching to Redis would share it across instances.

**The data layer scales independently.** Because the app reads its database from `DATABASE_URL`, moving from SQLite to Render Postgres needs no code change. Postgres in turn can add read replicas or partitioning without touching the API.

## 4. Modularity

- **Blueprints per resource:** `devices.py`, `readings.py`, `stats.py`, and `health.py` each own one responsibility and are registered under their own URL prefix.
- **App factory:** `create_app(config_class)` builds the app from a config object. The tests use this to create an isolated app with an in-memory database (`TestConfig`), with no change to production code.
- **Separated concerns:** configuration (`config.py`), extensions (`extensions.py`), models (`models.py`), and seed data (`seed.py`) are independent modules.
- **Versioning:** all routes sit under `/api/v1/`. A future `/api/v2/` can change response shapes without breaking existing consumers.
- **Path to microservices:** if `stats` became a bottleneck, its blueprint could be extracted into its own service and scaled separately. The URL contract would stay the same.

## 5. Loose Coupling

Components interact only through the HTTP contract (URL, method, parameters, JSON schema).

| Benefit | Evidence in this project |
|---|---|
| **Replaceable backend** | SQLite to Postgres is one environment variable. Clients are unaffected. |
| **Independent consumers** | `fetch_all.py` uses only `requests` and the JSON format. A Spark job, a notebook, or a dashboard could use the same endpoints. CORS is enabled for `/api/*`, so browser front ends can call it too. |
| **Independent scaling** | The API tier (gunicorn workers), the data tier (database), and the analysis tier (the client or Spark) scale separately. |
| **Fault isolation** | Errors return consistent JSON (`400`, `404`, `500`), and the client uses timeouts and `raise_for_status()`, so one failing request does not corrupt the rest of a pull. |
| **Independent deployment** | A push to GitHub redeploys the API on Render. Consumers need no change if the contract is unchanged. |

This follows the common big-data pattern of separating storage, compute, and access. The API is the access layer. Parquet files in object storage and a Spark cluster could handle the heavy processing behind or beside it.

## 6. Operational Advantages

- **Automated deployment:** `autoDeploy: true` in `render.yaml` means every push to the connected branch builds and releases the new version.
- **Health checking:** `/health` is a cheap endpoint that Render uses to confirm the service is up, and an uptime pinger can use it too.
- **Testing:** 11 pytest tests cover pagination, the page-size cap, filtering, validation, 404 handling, record creation, aggregates, and the units metadata. HTTP-based design makes these tests simple, because they use Flask's test client with no running server.
- **Single controlled entry point:** clients never access the database directly. Validation lives in the API (for example, `humidity` must be between 0 and 100, and `device_id` must exist).

## 7. Problem Found During Testing

While running the API under gunicorn with 2 workers, the API reported 40,000 readings and 10 devices instead of 20,000 and 5. Each worker started the app, saw an empty database at the same time, and seeded it. This is a race condition that only appears once a service runs several workers, and Render would have hit it too.

**Fix:** start gunicorn with `--preload` (`gunicorn wsgi:app --preload --workers 2`). The app is then built once in the master process before the workers fork, so seeding happens once. After the fix, the count was 20,000.

**Lesson:** scaling out exposes assumptions that hold with a single process. Startup work such as seeding or migrations must run once, not once per worker. In a larger system, a separate migration step would replace seeding at startup.

## 8. Measured Results on Render

The API was deployed to Render's free tier (Oregon region, Python 3, 2 gunicorn workers) at `https://sensor-api-wrmk.onrender.com` and tested from a laptop on 2 November 2026.

**Correctness after deployment.** `GET /api/v1/stats/summary` returned `count: 20000`, with average temperature 17.97 and average humidity 45.02. The count confirms that the `--preload` fix from Section 7 works in production. The two workers seeded the database once.

These measurements were taken before the `units` metadata was added. It adds about 40 bytes per response, which is negligible next to the 9.5 to 95.6 KB list payloads.

**Response times** (5 requests per endpoint, warm service):

| Endpoint | Avg | Min | Max | Payload |
|---|---|---|---|---|
| `/health` | 0.330 s | 0.315 s | 0.340 s | 16 B |
| `/readings?limit=100` | 0.347 s | 0.333 s | 0.368 s | 9.5 KB |
| `/readings?limit=1000` | 0.463 s | 0.396 s | 0.553 s | 95.6 KB |
| `/stats/summary` | 0.319 s | 0.307 s | 0.331 s | 110 B |

**Full ingestion** (`client/fetch_all.py`, 3 runs): 20,000 rows in 5.4 s, 5.9 s, and 5.4 s. That is 20 requests of 1,000 rows, about 1.9 MB in total, or roughly 0.27 to 0.30 s per request.

**What the numbers show**
- **Network round-trip dominates.** An empty `/health` call already costs about 0.33 s. Going from 100 to 1,000 rows (10 times the payload) adds only about 0.12 s. The per-request overhead is much larger than the cost of the data itself, so larger pages are more efficient for bulk pulls, which supports the 1,000-row cap.
- **Cost scales with the number of pages.** 20 sequential requests take about 5.5 s, so a 10 times larger dataset would take about 55 s sequentially. Fetching pages in parallel (for example from Spark workers, each taking an offset range) is the natural next step.
- **The stats cache is not visible in these numbers.** `/stats/summary` takes about as long as `/health` because the network latency hides the cost of a 20,000-row aggregate. The cache would matter more with millions of rows or a slower database.
- **Cold start was not observed.** The service was already awake when tested (first request 0.48 s), so the 30 to 60 s cold start described for the free tier remains a documented limitation, not a measurement. It can be measured by calling the API after more than 15 minutes of inactivity.

## 9. Limitations at Scale

| Limitation | Detail | Mitigation |
|---|---|---|
| **Cold starts** | Render's free tier sleeps after about 15 minutes idle. The first request takes 30 to 60 seconds (documented behavior, not measured here). | The client uses a 90 s timeout. Use a paid plan or a pinger on `/health`. |
| **Ephemeral storage** | SQLite data is lost on restart. The app re-seeds itself. | Use Render Postgres through `DATABASE_URL`. |
| **Offset pagination** | Deep pages get slower, because the database must skip all earlier rows. | Keyset pagination (`WHERE id > last_id`). |
| **Synchronous workers** | Concurrency is limited by the worker count. | More workers or instances, or a task queue (Celery, Redis Queue) for long jobs. |
| **JSON for bulk data** | Verbose and slow for very large transfers. | Export to Parquet in object storage and read it directly from Spark. |
| **Real-time streams** | Request/response does not suit continuous sensor events. | Kafka or MQTT for ingestion, with REST for queries. |
| **No authentication** | Anyone can call `POST /readings`. | Add API keys or JWT before exposing write endpoints. |
| **Cache staleness** | `POST /readings` does not clear the stats cache, so stats can be up to 30 s old. | Invalidate on write, or accept short staleness. |

## 10. Summary

| Aspect | How the project demonstrates it |
|---|---|
| **Scalability** | Stateless design with 2 gunicorn workers, bounded pages (max 1,000 rows), cached aggregates, and a database that can be swapped through one environment variable |
| **Modularity** | Blueprints per resource, an app factory, separate config/models/seed modules, and `/api/v1` versioning |
| **Loose coupling** | A pure HTTP/JSON contract lets the client, database, and hosting change independently |
| **Trade-offs** | Free-tier cold starts, ephemeral storage, offset pagination, and JSON overhead, each with a known mitigation |

The RESTful Flask approach trades some raw performance for flexibility. The result is a system that is easy to grow, change, and integrate, and where bottlenecks can be fixed one component at a time. For much larger volumes, it should be complemented by streaming (Kafka), object storage (S3 with Parquet), and a distributed processing engine (Spark).

## Appendix: Reproducing the Results

```bash
pip install -r requirements.txt
pytest                                                     # 11 tests pass
gunicorn wsgi:app --preload --workers 2 --bind 127.0.0.1:5055
python client/fetch_all.py http://127.0.0.1:5055           # fetched 20000 rows in ~0.2 s (local)
python client/fetch_all.py https://sensor-api-wrmk.onrender.com   # 5.4 to 5.9 s (Render)
```

The local run takes about 0.2 s because there is no network latency. Against Render, each request adds about 0.3 s of round-trip time. The first request after more than 15 minutes of idle time would also include the free-tier cold start.
