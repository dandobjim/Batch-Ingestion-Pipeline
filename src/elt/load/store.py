from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds

from elt.extraction.models.fetch_issues_response_model import Issue

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "source=github_api"


def save_raw(issues: list[Issue]) -> None:
    ingestion_date = datetime.now(UTC).date().isoformat()
    records = [
        {**issue.model_dump(mode="json"), "ingestion_date": ingestion_date}
        for issue in issues
    ]
    table = pa.Table.from_pylist(records)

    ds.write_dataset(
        table,
        base_dir=RAW_DATA_DIR,
        format="parquet",
        partitioning=["ingestion_date"],
        existing_data_behavior="overwrite_or_ignore",
    )