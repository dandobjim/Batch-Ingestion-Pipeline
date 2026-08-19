# Batch Data Ingestion Pipeline

[![forthebadge made-with-python](http://ForTheBadge.com/images/badges/made-with-python.svg)](https://www.python.org/)
![Static Badge](https://img.shields.io/badge/python_3.14-green)
![Static Badge](https://img.shields.io/badge/orchestration-Airflow_3.3-017CEE)
![Static Badge](https://img.shields.io/badge/transform-dbt_1.11-FF694B)
![Static Badge](https://img.shields.io/badge/status-pre--alpha-lightgrey)
![Static Badge](https://img.shields.io/badge/license-Apache_2.0-blue)

## Summary

A batch ELT pipeline that pulls issues from the GitHub REST API, validates them against a
strict schema, and lands them in a partitioned raw Parquet layer. From there, the data is
loaded into Postgres and transformed by dbt into a clean, typed staging layer — all
orchestrated end-to-end by Apache Airflow and reproducible with a single `docker compose up`.

It's a small, deliberately concrete reference implementation of the **extract → validate →
raw → load → transform** shape most batch pipelines follow, built to be read end-to-end in
one sitting.

## Architecture

```mermaid
flowchart LR
    GH["GitHub REST API<br/>/repos/:owner/:repo/issues"]

    subgraph ELT["Python ELT package (src/elt)"]
        direction TB
        EX["Extraction<br/>GithubIssuesClient"]
        VA["Schema validation<br/>Pydantic Issue model"]
        WR["Raw writer<br/>ParquetIssueWriter"]
        LD["Warehouse loader<br/>DuckDB"]
    end

    PQ[("Raw layer<br/>Parquet, partitioned by<br/>ingestion_date")]

    subgraph PG["Postgres (postgres-dbt)"]
        direction TB
        RAW[("raw.github_issues")]
        STG[("stg.stg_github_issues")]
    end

    DBT["dbt project<br/>dbt_batch_ingestion"]
    DAG["Airflow DAG<br/>github_issues_batch_ingestion"]
    API["FastAPI<br/>(planned) trigger / metadata endpoint"]

    GH --> EX --> VA --> WR --> PQ
    PQ --> LD --> RAW
    RAW --> DBT --> STG

    DAG -. orchestrates .-> EX
    DAG -. orchestrates .-> WR
    DAG -. orchestrates .-> LD
    DAG -. orchestrates .-> DBT
    API -. triggers / monitors .-> DAG
```

**Layers:**

- **Extraction** (`src/elt/extraction`) — `GithubIssuesClient` paginates the GitHub Issues
  API, transparently retrying on rate limits (`429`/`403` with `Retry-After` or
  `X-RateLimit-Reset`) with exponential backoff as a fallback.
- **Schema validation** — inline, not a separate step: each page is parsed straight into the
  `Issue` Pydantic model (`src/elt/extraction/models`), so malformed API responses fail fast.
- **Raw layer** (`src/elt/load/store.py`) — `ParquetIssueWriter` writes a Hive-partitioned
  Parquet dataset (`data/raw/source=github_api/ingestion_date=YYYY-MM-DD/`), the
  source of truth for everything downstream.
- **Warehouse load** (`src/elt/load/load_to_warehouse.py`) — an in-process DuckDB connection
  attaches to Postgres over the `postgres` extension and upserts a single partition
  (delete + insert, wrapped in a transaction) into `raw.github_issues`.
- **Staging layer** (`dbt_batch_ingestion/`) — a dbt model (`stg_github_issues`) dedupes by
  `id` (keeping the latest `_loaded_at`), renames columns, and casts the JSON `reactions` /
  `user` / `labels` payloads into typed columns.
- **Orchestration** — an Airflow 3 DAG (`dags/github_issues_pipeline.py`) chains all of the
  above as four tasks; see [Pipeline Flow](#pipeline-flow).
- **API** — a FastAPI trigger/metadata endpoint is planned (`src/api/`) but not implemented
  yet.

## Pipeline Flow

```mermaid
flowchart TD
    A["extract_issues<br/>Fetch + validate all pages<br/>for {owner}/{repo}"]
    B["write_raw_parquet<br/>Write Hive-partitioned Parquet<br/>partition = ingestion_date"]
    C["load_raw_to_warehouse<br/>DuckDB: DELETE + INSERT partition<br/>into Postgres raw.github_issues"]
    D["build_staging_layer<br/>dbt run --select stg_github_issues<br/>-> Postgres stg.stg_github_issues"]

    A --> B --> C --> D
```

Each task's output is exactly what the next one needs, and nothing more: `extract_issues`
hands off validated issues over XCom, `write_raw_parquet` returns the `ingestion_date`
partition it just wrote, and everything downstream operates on that one partition — so
re-running a day is idempotent (the load step deletes the partition before re-inserting it).

## Tech Stack & Dependencies

| Layer | Technology |
|---|---|
| Language | Python 3.14 |
| Extraction / validation | `requests`, `pydantic`, `pydantic-settings` |
| Raw storage | Apache Parquet via `pyarrow` (Hive partitioning) |
| Warehouse load | `duckdb` (Postgres attach) |
| Data warehouse | PostgreSQL 16 |
| Transformation | `dbt-postgres` |
| Orchestration | Apache Airflow 3.3 (CeleryExecutor, Redis broker) |
| API (planned) | FastAPI |
| Logging | `structlog` |
| Testing | `pytest`, `pytest-cov` |
| Linting / formatting | `ruff` |
| Package management | [`uv`](https://docs.astral.sh/uv/) |
| Local infra | Docker Compose |

Full, pinned dependency list: [`pyproject.toml`](./pyproject.toml) /
[`uv.lock`](./uv.lock).

## Project Structure

```
.
├── dags/                        # Airflow DAGs
│   └── github_issues_pipeline.py
├── src/
│   ├── elt/
│   │   ├── config/               # Env var settings, logging
│   │   ├── extraction/           # GithubIssuesClient + Pydantic models
│   │   ├── load/                 # ParquetIssueWriter, DuckDB -> Postgres loader
│   │   └── transform/            # (reserved for in-Python transforms)
│   ├── db/scripts/                # Raw schema DDL (raw.github_issues)
│   └── api/                       # FastAPI app (planned, not yet implemented)
├── dbt_batch_ingestion/          # dbt project (staging models, sources, profile)
├── tests/                        # unit + integration tests, mirrors src/
├── docker-compose.yaml           # Airflow + Postgres (metadata & warehouse) + Redis
├── Dockerfile                    # Airflow image extended with duckdb/dbt-postgres
└── .env.example
```

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Python 3.14
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- A GitHub [personal access token](https://github.com/settings/tokens) (no special scopes
  needed for public repos)

### 1. Clone and configure

```bash
git clone https://github.com/dandobjim/Batch-Ingestion-Pipeline.git
cd Batch-Ingestion-Pipeline
cp .env.example .env
```

Edit `.env` and set:

| Variable | Used by | Example |
|---|---|---|
| `GITHUB_API_KEY` | extraction | your GitHub personal access token |
| `DATABASE_URL` | warehouse load, dbt | `postgresql://test:test@localhost:5432/github_db` |

`docker-compose.yaml` overrides `DATABASE_URL` to `postgresql://test:test@postgres-dbt:5432/github_db`
*inside* the Airflow containers (where `localhost` doesn't resolve to the Postgres
container) — the `.env` value is only used for host-side runs.

### 2. Install Python dependencies

```bash
uv sync
```

### 3. Start the stack

```bash
docker compose up -d --build
```

This builds the custom Airflow image (adds `duckdb` and `dbt-postgres`, see
[`Dockerfile`](./Dockerfile)) and brings up Airflow (CeleryExecutor), Redis, the Airflow
metadata Postgres, and a second Postgres instance (`postgres-dbt`) that acts as the
warehouse. Airflow's web UI is at **http://localhost:8080** (default credentials:
`airflow` / `airflow`).

### 4. Bootstrap the warehouse schema

The raw table isn't created automatically yet — run the DDL once against the warehouse
container:

```bash
docker compose exec -T postgres-dbt psql -U test -d github_db < src/db/scripts/init_db_raw.sql
```

### 5. Configure dbt for local (non-Docker) runs

The DAG's `dbt run` task uses the profile committed at
[`dbt_batch_ingestion/profiles.yml`](./dbt_batch_ingestion/profiles.yml) (host defaults to
`postgres-dbt`, the Docker service name). To run dbt from your host instead, add a matching
profile to `~/.dbt/profiles.yml` pointing at `localhost`:

```yaml
dbt_batch_ingestion:
  target: dev
  outputs:
    dev:
      type: postgres
      host: localhost
      port: 5432
      user: test
      pass: test
      dbname: github_db
      schema: stg
      threads: 4
```

### 6. Run the pipeline

**Via Airflow** (recommended — this is what the DAG is for):

```bash
docker compose exec airflow-worker airflow dags unpause github_issues_batch_ingestion
docker compose exec airflow-worker airflow dags trigger github_issues_batch_ingestion
```

Or trigger it from the UI at http://localhost:8080. The `owner`/`repo` GitHub repository to
ingest are DAG params (default: `react`/`react`), overridable per run.

**Or step by step, from the host** (useful for local development):

```bash
uv run python -m elt.load.load_to_warehouse   # extract -> parquet -> warehouse, see __main__
cd dbt_batch_ingestion && uv run dbt run --select stg_github_issues
```

## Testing

```bash
uv run pytest                 # full suite
uv run pytest -m unit         # fast, isolated, no I/O
uv run pytest -m integration  # end-to-end flow, mocked HTTP, real filesystem
uv run pytest --cov           # with coverage (see [tool.coverage] in pyproject.toml)
```

## Linting

```bash
uv run ruff check .
uv run ruff format .
```

## Status & Roadmap

This project is in active, early development (`Development Status :: 2 - Pre-Alpha`).

- [x] GitHub issues extraction with pagination and rate-limit handling
- [x] Pydantic schema validation
- [x] Partitioned raw Parquet layer
- [x] Warehouse load (DuckDB → Postgres)
- [x] dbt staging layer
- [x] Airflow orchestration (`dags/github_issues_pipeline.py`)
- [ ] FastAPI trigger/metadata endpoint (`src/api/`)
- [ ] Automated raw-schema bootstrap (currently a manual `psql` step, see [above](#4-bootstrap-the-warehouse-schema))

## License

[Apache License 2.0](./LICENSE)
