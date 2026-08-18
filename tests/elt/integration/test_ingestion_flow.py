"""End-to-end ingestion flow: extract -> load, fully mocked HTTP, real files.

The two components are chained directly, with no orchestration layer in
between — the same shape a two-task Airflow DAG would have.
"""

from unittest.mock import MagicMock

import pyarrow.dataset as ds
import pytest
import requests

from elt.extraction.extract import GithubIssuesClient
from elt.extraction.models.fetch_issues_response_model import Issue
from elt.load.store import ParquetIssueWriter

BASE_URL = "https://fake.test"
PARTITION_NAME = "ingestion_date=2026-01-15"


def make_client(session, frozen_time, **kwargs) -> GithubIssuesClient:
    return GithubIssuesClient(
        session,
        base_url=BASE_URL,
        sleep=kwargs.pop("sleep", MagicMock()),
        time_source=frozen_time,
        **kwargs,
    )


def read_back(base_dir):
    return ds.dataset(base_dir, format="parquet", partitioning="hive").to_table()


class TestIngestionFlow:
    def test_fetches_paginated_issues_and_writes_hive_partitioned_parquet(
        self, tmp_path, paginated_session, issues_request, frozen_clock, frozen_time
    ):
        client = make_client(paginated_session, frozen_time)
        writer = ParquetIssueWriter(tmp_path, clock=frozen_clock)

        issues = client.fetch_issues(issues_request)
        writer.write(issues)

        assert len(issues) == 5
        assert paginated_session.get.call_count == 2

        partition_dir = tmp_path / PARTITION_NAME
        assert partition_dir.is_dir()
        assert list(partition_dir.glob("*.parquet"))

        table = read_back(tmp_path)
        assert table.num_rows == 5
        assert set(table.column("ingestion_date").to_pylist()) == {"2026-01-15"}
        assert sorted(table.column("id").to_pylist()) == [1, 2, 3, 4, 5]

    def test_reactions_stored_under_field_names_not_api_aliases(
        self, tmp_path, paginated_session, issues_request, frozen_clock, frozen_time
    ):
        client = make_client(paginated_session, frozen_time)
        ParquetIssueWriter(tmp_path, clock=frozen_clock).write(
            client.fetch_issues(issues_request)
        )

        reactions = read_back(tmp_path).schema.field("reactions").type
        children = {reactions.field(i).name for i in range(reactions.num_fields)}
        assert {"thumbs_up", "thumbs_down"} <= children
        assert not {"+1", "-1"} & children

    def test_round_trips_issue_values(
        self, tmp_path, paginated_session, issues_request, frozen_clock, frozen_time
    ):
        client = make_client(paginated_session, frozen_time)
        issues = client.fetch_issues(issues_request)
        ParquetIssueWriter(tmp_path, clock=frozen_clock).write(issues)

        table = read_back(tmp_path)
        rows = {row["id"]: row for row in table.to_pylist()}
        expected = issues[0]
        row = rows[expected.id]

        assert row["title"] == expected.title
        assert row["state"] == expected.state
        assert row["html_url"] == expected.html_url
        assert isinstance(row["created_at"], str)
        assert row["created_at"] == expected.model_dump(mode="json")["created_at"]

    def test_schema_contains_all_issue_fields(
        self, tmp_path, paginated_session, issues_request, frozen_clock, frozen_time
    ):
        client = make_client(paginated_session, frozen_time)
        ParquetIssueWriter(tmp_path, clock=frozen_clock).write(
            client.fetch_issues(issues_request)
        )

        expected = set(Issue.model_fields) | {"ingestion_date"}
        assert set(read_back(tmp_path).schema.names) == expected

    def test_recovers_from_transient_rate_limiting(
        self,
        tmp_path,
        make_response,
        page_one,
        page_two,
        issues_request,
        frozen_clock,
        frozen_time,
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [
            make_response(status_code=429, headers={"Retry-After": "1"}),
            page_one,
            page_two,
        ]
        sleep = MagicMock()
        client = make_client(session, frozen_time, sleep=sleep)

        issues = client.fetch_issues(issues_request)
        ParquetIssueWriter(tmp_path, clock=frozen_clock).write(issues)

        sleep.assert_called_once_with(1.0)
        assert session.get.call_count == 3
        assert read_back(tmp_path).num_rows == 5

    def test_writes_nothing_when_api_returns_no_issues(
        self, tmp_path, make_response, issues_request, frozen_clock, frozen_time
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(json_body=[])]
        client = make_client(session, frozen_time)

        issues = client.fetch_issues(issues_request)
        ParquetIssueWriter(tmp_path, clock=frozen_clock).write(issues)

        assert issues == []
        assert list(tmp_path.iterdir()) == []

    def test_http_error_aborts_before_write(
        self,
        tmp_path,
        make_response,
        page_one,
        issues_request,
        frozen_clock,
        frozen_time,
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [page_one, make_response(status_code=500)]
        client = make_client(session, frozen_time)
        writer = ParquetIssueWriter(tmp_path, clock=frozen_clock)

        with pytest.raises(requests.HTTPError):
            writer.write(client.fetch_issues(issues_request))

        assert list(tmp_path.iterdir()) == []
