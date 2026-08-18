"""Shared test fixtures and collection hooks.

Nothing here touches the network, the wall clock or the developer's ``.env``.
"""

import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

TESTS_DIR = Path(__file__).parent
if str(TESTS_DIR) not in sys.path:
    # Makes ``import factories`` work regardless of pytest's import mode.
    sys.path.insert(0, str(TESTS_DIR))

from elt.config.env_vars_config import get_env_vars  # noqa: E402
from elt.extraction.models.fetch_issues_request_model import IssuesRequest  # noqa: E402

FIXTURES_DIR = TESTS_DIR / "fixtures"
FROZEN_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def pytest_collection_modifyitems(items):
    """Mark by directory, so no test file has to remember to do it."""
    for item in items:
        path = str(item.path).replace(os.sep, "/")
        if "/integration/" in path:
            item.add_marker(pytest.mark.integration)
        elif "/unit/" in path:
            item.add_marker(pytest.mark.unit)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_env_vars.cache_clear()
    yield
    get_env_vars.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """No test may read the developer's real GITHUB_API_KEY."""
    monkeypatch.delenv("GITHUB_API_KEY", raising=False)


@pytest.fixture
def frozen_clock() -> Callable[[], datetime]:
    return lambda: FROZEN_NOW


@pytest.fixture
def frozen_time() -> Callable[[], float]:
    return lambda: FROZEN_NOW.timestamp()


@pytest.fixture
def make_response():
    """Builds a REAL ``requests.Response`` with no network involved."""

    def _make(
        *,
        status_code: int = 200,
        json_body=None,
        headers: dict | None = None,
        url: str = "https://fake.test/repos/octo/hello/issues",
        content: bytes | None = None,
    ) -> requests.Response:
        response = requests.Response()
        response.status_code = status_code
        response.reason = "OK" if status_code < 400 else "Error"
        response.url = url
        response.encoding = "utf-8"
        response.headers.update(headers or {})
        if content is None:
            body = json_body if json_body is not None else []
            content = json.dumps(body).encode()
        response._content = content
        return response

    return _make


@pytest.fixture
def issues_request() -> IssuesRequest:
    return IssuesRequest(owner="octo", repo="hello", api_key="test-token", per_page=100)
