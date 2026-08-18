from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds

from elt.config.logging_configuration import log
from elt.extraction.models.fetch_issues_response_model import Issue
from elt.ports import Clock

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "source=github_api"
PARTITION_SCHEMA = pa.schema([("ingestion_date", pa.string())])


def utc_now() -> datetime:
    return datetime.now(UTC)


class ParquetIssueWriter:
    """Writes validated issues as a Hive-partitioned Parquet dataset.

    Designed to be driven as an Airflow task.
    """

    def __init__(
        self,
        base_dir: Path | str = RAW_DATA_DIR,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._clock = clock

    def write(self, issues: list[Issue]) -> None:
        if not issues:
            log.warning("No issues to write, skipping parquet write")
            return

        ingestion_date = self._clock().date().isoformat()
        records = [
            {**issue.model_dump(mode="json"), "ingestion_date": ingestion_date}
            for issue in issues
        ]
        table = pa.Table.from_pylist(records)

        ds.write_dataset(
            table,
            base_dir=self._base_dir,
            format="parquet",
            partitioning=ds.partitioning(PARTITION_SCHEMA, flavor="hive"),
            existing_data_behavior="overwrite_or_ignore",
        )
        log.info(
            f"Wrote {len(records)} issues to {self._base_dir} "
            f"partition ingestion_date={ingestion_date}"
        )
