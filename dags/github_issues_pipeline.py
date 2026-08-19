"""GitHub issues batch ingestion DAG.

Mirrors the architecture described in the project README:

    External API -> Extraction script (Python) -> Schema validation (Pydantic)
    -> Raw layer (Parquet, partitioned by date) -> Staging layer (cleaned & typed)

Schema validation happens inline during extraction (`GithubIssuesClient.fetch_issues`
parses each page through the `Issue` Pydantic model), so it isn't a separate task.
"""

import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

DBT_PROJECT_DIR = "/opt/airflow/dbt_batch_ingestion"


@dag(
    dag_id="github_issues_batch_ingestion",
    description=(
        "Extracts GitHub issues, validates them against the Issue schema, lands "
        "them in a partitioned raw Parquet layer, and builds the staging layer."
    ),
    schedule="@daily",
    start_date=datetime.datetime(2026, 1, 1),
    catchup=False,
    tags=["github", "elt", "batch"],
)
def github_issues_batch_ingestion(owner: str = "react", repo: str = "react"):
    @task
    def extract_issues(owner: str, repo: str) -> list[dict]:
        """External API -> Extraction script (+ inline Pydantic schema validation)."""
        from elt.config.env_vars_config import get_env_vars
        from elt.extraction.extract import GithubIssuesClient
        from elt.extraction.models.fetch_issues_request_model import IssuesRequest

        request = IssuesRequest(owner=owner, repo=repo, api_key=get_env_vars().api_key)
        issues = GithubIssuesClient().fetch_issues(request)
        # by_alias=True: round-trips through XCom in the shape Issue.model_validate
        # expects back (e.g. reactions' "+1"/"-1" aliases), since Reactions doesn't
        # set populate_by_name.
        return [issue.model_dump(mode="json", by_alias=True) for issue in issues]

    @task
    def write_raw_parquet(issues: list[dict]) -> str:
        """Raw layer - Parquet, partitioned by date."""
        from elt.extraction.models.fetch_issues_response_model import Issue
        from elt.load.store import ParquetIssueWriter, utc_now

        ingestion_date = utc_now().date().isoformat()
        ParquetIssueWriter().write([Issue.model_validate(issue) for issue in issues])
        return ingestion_date

    @task
    def load_raw_to_warehouse(ingestion_date: str) -> str:
        """Lands the raw Parquet partition in Postgres so dbt can read it as a source."""
        from elt.config.env_vars_config import get_env_vars
        from elt.load.load_to_warehouse import load_partition_to_warehouse
        from elt.load.store import RAW_DATA_DIR

        load_partition_to_warehouse(
            ingestion_date=ingestion_date,
            parquet_glob=str(
                RAW_DATA_DIR / f"ingestion_date={ingestion_date}" / "part-*.parquet"
            ),
            pg_conn_str=get_env_vars().database_url,
        )
        return ingestion_date

    build_staging_layer = BashOperator(
        task_id="build_staging_layer",
        bash_command=(
            f"cd {DBT_PROJECT_DIR} && "
            f"dbt run --select stg_github_issues --profiles-dir {DBT_PROJECT_DIR}"
        ),
    )

    ingestion_date = write_raw_parquet(extract_issues(owner, repo))
    load_raw_to_warehouse(ingestion_date) >> build_staging_layer


github_issues_batch_ingestion()
