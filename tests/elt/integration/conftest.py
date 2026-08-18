"""Integration-only fixtures: a fully mocked, paginated GitHub session."""

from unittest.mock import MagicMock

import pytest
import requests
from factories import make_issues_page

BASE_URL = "https://fake.test"
PAGE_TWO_URL = "https://fake.test/repos/octo/hello/issues?page=2"
NEXT_LINK = {"Link": f'<{PAGE_TWO_URL}>; rel="next"'}


@pytest.fixture
def page_one(make_response):
    return make_response(json_body=make_issues_page(3, start_id=1), headers=NEXT_LINK)


@pytest.fixture
def page_two(make_response):
    return make_response(json_body=make_issues_page(2, start_id=4))


@pytest.fixture
def paginated_session(page_one, page_two):
    """Two pages joined by a ``Link: ...; rel="next"`` header, 5 issues total."""
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = [page_one, page_two]
    return session
