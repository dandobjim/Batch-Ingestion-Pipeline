"""Unit tests for the Hive-partitioned Parquet writer."""

from datetime import UTC, datetime

import pyarrow.dataset as ds
import structlog
from factories import make_issue

from elt.load.store import RAW_DATA_DIR, ParquetIssueWriter, utc_now

PARTITION_NAME = "ingestion_date=2026-01-15"


def read_back(base_dir):
    return ds.dataset(base_dir, format="parquet", partitioning="hive").to_table()


class TestParquetIssueWriterDefaults:
    def test_defaults_to_the_project_raw_data_dir(self):
        """Must not write anything: never touch the repo's ``data/``."""
        assert ParquetIssueWriter()._base_dir == RAW_DATA_DIR

    def test_default_clock_returns_an_aware_utc_datetime(self):
        assert utc_now().tzinfo is UTC


class TestParquetIssueWriterWrite:
    def test_creates_hive_partition_named_from_the_injected_clock(
        self, tmp_path, frozen_clock
    ):
        ParquetIssueWriter(tmp_path, clock=frozen_clock).write([make_issue()])

        partition_dir = tmp_path / PARTITION_NAME
        assert partition_dir.is_dir()
        assert list(partition_dir.glob("*.parquet"))

    def test_creates_base_dir_when_missing(self, tmp_path, frozen_clock):
        base_dir = tmp_path / "does" / "not" / "exist"

        ParquetIssueWriter(base_dir, clock=frozen_clock).write([make_issue()])

        assert (base_dir / PARTITION_NAME).is_dir()

    def test_writes_one_row_per_issue(self, tmp_path, frozen_clock):
        issues = [make_issue(id=i, number=i) for i in range(1, 4)]

        ParquetIssueWriter(tmp_path, clock=frozen_clock).write(issues)

        table = read_back(tmp_path)
        assert table.num_rows == 3
        assert sorted(table.column("id").to_pylist()) == [1, 2, 3]

    def test_ingestion_date_column_is_readable_with_hive_partitioning(
        self, tmp_path, frozen_clock
    ):
        """The concrete proof that the Hive migration was worth it."""
        issues = [make_issue(id=i, number=i) for i in range(1, 4)]

        ParquetIssueWriter(tmp_path, clock=frozen_clock).write(issues)

        table = read_back(tmp_path)
        assert "ingestion_date" in table.schema.names
        assert set(table.column("ingestion_date").to_pylist()) == {"2026-01-15"}

    def test_reactions_struct_uses_field_names_not_api_aliases(
        self, tmp_path, frozen_clock
    ):
        ParquetIssueWriter(tmp_path, clock=frozen_clock).write([make_issue()])

        reactions = read_back(tmp_path).schema.field("reactions").type
        children = {reactions.field(i).name for i in range(reactions.num_fields)}
        assert {"thumbs_up", "thumbs_down"} <= children
        assert "+1" not in children
        assert "-1" not in children

    def test_rerun_on_the_same_day_does_not_duplicate_rows(
        self, tmp_path, frozen_clock
    ):
        issues = [make_issue(id=i, number=i) for i in range(1, 4)]
        writer = ParquetIssueWriter(tmp_path, clock=frozen_clock)

        writer.write(issues)
        writer.write(issues)

        assert read_back(tmp_path).num_rows == 3

    def test_different_clocks_produce_separate_partitions(self, tmp_path):
        other_day = datetime(2026, 1, 16, 12, 0, 0, tzinfo=UTC)

        ParquetIssueWriter(
            tmp_path, clock=lambda: datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        ).write([make_issue(id=1, number=1)])
        ParquetIssueWriter(tmp_path, clock=lambda: other_day).write(
            [make_issue(id=2, number=2)]
        )

        assert (tmp_path / "ingestion_date=2026-01-15").is_dir()
        assert (tmp_path / "ingestion_date=2026-01-16").is_dir()
        assert read_back(tmp_path).num_rows == 2


class TestParquetIssueWriterEmptyInput:
    def test_writes_nothing_for_an_empty_list(self, tmp_path, frozen_clock):
        ParquetIssueWriter(tmp_path, clock=frozen_clock).write([])

        assert list(tmp_path.iterdir()) == []

    def test_logs_a_warning_for_an_empty_list(self, tmp_path, frozen_clock):
        with structlog.testing.capture_logs() as logs:
            ParquetIssueWriter(tmp_path, clock=frozen_clock).write([])

        assert [entry["log_level"] for entry in logs] == ["warning"]
