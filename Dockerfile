FROM apache/airflow:3.3.1

RUN pip install --no-cache-dir "duckdb>=1.5.5" "dbt-postgres>=1.11.0"

ENV PYTHONPATH="/opt/airflow/src"
