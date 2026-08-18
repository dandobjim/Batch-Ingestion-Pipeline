"""Test data factories built on top of a real captured GitHub payload.

Rationale: ``Issue`` requires ~20 ``GithubUser`` fields and uses the API
aliases ``"+1"``/``"-1"`` on ``Reactions``, so hand-written literals are huge
and drift away from the real API. The base page is a verbatim (scrubbed)
capture of a ``200`` response from ``GET /repos/facebook/react/issues``.
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from elt.extraction.models.fetch_issues_response_model import Issue

FIXTURES_DIR = Path(__file__).parent / "fixtures"

with (FIXTURES_DIR / "github_issues_page.json").open(encoding="utf-8") as _handle:
    _BASE_PAGE: list[dict[str, Any]] = json.load(_handle)

#: Index 0 is a pull request (non-null ``pull_request``, ``draft`` present).
PULL_REQUEST_INDEX = 0
#: Index 1 is a plain issue with ``milestone: null``.
PLAIN_ISSUE_INDEX = 1


def base_page() -> list[dict[str, Any]]:
    """Deep copy of the full captured page (2 issues, every field kept)."""
    return deepcopy(_BASE_PAGE)


def make_issue_payload(**overrides: Any) -> dict[str, Any]:
    """Raw, complete and valid issue dict with top-level overrides.

    CAREFUL: ``reactions`` uses the API aliases ``"+1"``/``"-1"``, NOT
    ``thumbs_up``/``thumbs_down`` — ``populate_by_name`` is not enabled on the
    model, so passing the field names raises ``ValidationError``.

    No deep merge on purpose: it is magic that hides which fields a test
    actually cares about. Override a nested key by building the dict yourself.
    """
    payload = deepcopy(_BASE_PAGE[PULL_REQUEST_INDEX])
    payload.update(overrides)
    return payload


def make_plain_issue_payload(**overrides: Any) -> dict[str, Any]:
    """Same as :func:`make_issue_payload` but based on the non-PR issue."""
    payload = deepcopy(_BASE_PAGE[PLAIN_ISSUE_INDEX])
    payload.update(overrides)
    return payload


def make_issue(**overrides: Any) -> Issue:
    return Issue.model_validate(make_issue_payload(**overrides))


def make_issues_page(count: int = 2, *, start_id: int = 1) -> list[dict[str, Any]]:
    return [
        make_issue_payload(id=start_id + i, number=start_id + i) for i in range(count)
    ]
