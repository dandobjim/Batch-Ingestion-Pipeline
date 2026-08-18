# Batch Data Ingestion Pipeline
[![forthebadge made-with-python](http://ForTheBadge.com/images/badges/made-with-python.svg)](https://www.python.org/)
![Static Badge](https://img.shields.io/badge/python_3.14-green)

## Overview

A batch pipeline that extracts data from a public API and/or CSV sources, validates it against a schema, and lands it in
a partitioned raw storage layer — fully orchestrated with Airflow.

## Architecture

```mermaid
flowchart LR
    A[External API / CSV source] --> B[Extraction script - Python]
    B --> C[Schema validation - Pydantic]
    C --> D[Raw layer - Parquet, partitioned by date]
    D --> E[Staging layer - cleaned & typed]
    F[Airflow DAG] -. orchestrates .-> B
    F -. orchestrates .-> C
    F -. orchestrates .-> D
    F -. orchestrates .-> E
    G[FastAPI] -. triggers/monitors .-> F
```

## Tech Stack
- Python 
- Pydantic
- Parquet
- Airflow
- FastAPI (trigger/metadata endpoint only)

