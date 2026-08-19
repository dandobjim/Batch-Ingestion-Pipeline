import duckdb

from elt.config.env_vars_config import get_env_vars
from elt.config.logging_configuration import log


def load_partition_to_warehouse(ingestion_date: str, parquet_glob: str, pg_conn_str: str):
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{pg_conn_str}' AS pg (TYPE postgres);")

    con.execute("BEGIN;")
    try:
        log.info("Parsing and loading data into warehouse")

        con.execute(f"""
                    DELETE FROM pg.raw.github_issues
                    WHERE ingestion_date = '{ingestion_date}';
                """)

        con.execute(f"""
                    INSERT INTO pg.raw.github_issues (
                        url, repository_url, labels_url, comments_url, events_url, html_url,
                        id, node_id, number, title, "user", labels, state, locked,
                        assignees, milestone, comments, created_at, updated_at, closed_at,
                        assignee, author_association, issue_field_values, "type",
                        active_lock_reason, draft, pull_request, body, closed_by, reactions,
                        timeline_url, performed_via_github_app, state_reason, pinned_comment,
                        sub_issues_summary, issue_dependencies_summary, ingestion_date
                    )
                    SELECT
                        url, repository_url, labels_url, comments_url, events_url, html_url,
                        id, node_id, number, title,
                        to_json("user")           AS "user",
                        to_json(labels)           AS labels,
                        state, locked,
                        to_json(assignees)        AS assignees,
                        to_json(milestone)        AS milestone,
                        comments,
                        created_at::TIMESTAMP,
                        updated_at::TIMESTAMP,
                        closed_at::TIMESTAMP,
                        to_json(assignee)         AS assignee,
                        author_association,
                        to_json(issue_field_values) AS issue_field_values,
                        to_json("type")           AS "type",
                        active_lock_reason, draft,
                        to_json(pull_request)     AS pull_request,
                        body,
                        to_json(closed_by)        AS closed_by,
                        to_json(reactions)        AS reactions,
                        timeline_url,
                        to_json(performed_via_github_app) AS performed_via_github_app,
                        state_reason,
                        to_json(pinned_comment)   AS pinned_comment,
                        to_json(sub_issues_summary) AS sub_issues_summary,
                        to_json(issue_dependencies_summary) AS issue_dependencies_summary,
                        CAST('{ingestion_date}' AS DATE) AS ingestion_date
                    FROM read_parquet('{parquet_glob}');
                """)
        con.execute("COMMIT;")
    except Exception:
        con.execute("ROLLBACK;")
        raise

    # Verification
    result = con.execute(f"""
            SELECT count(*) FROM pg.raw.github_issues
            WHERE ingestion_date = '{ingestion_date}'
        """).fetchone()
    log.info(f"Rows loaded for {ingestion_date}: {result[0]}")


if __name__ == "__main__":

    load_partition_to_warehouse(
        ingestion_date="2026-08-19",
        parquet_glob="data/raw/source=github_api/ingestion_date=2026-08-19/part-*.parquet",
        pg_conn_str=get_env_vars().database_url,
    )