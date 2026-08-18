"""Unit tests for the GitHub issues extraction layer."""

import json
from unittest.mock import MagicMock, call

import pytest
import requests
import structlog
from factories import make_issue_payload, make_issues_page
from pydantic import ValidationError

from elt.extraction.extract import (
    DEFAULT_TIMEOUT,
    GithubIssuesClient,
    _is_rate_limited,
    _seconds_until_retry,
)

BASE_URL = "https://fake.test"
ISSUES_URL = "https://fake.test/repos/octo/hello/issues"
PAGE_TWO_URL = "https://fake.test/repos/octo/hello/issues?page=2"


def next_link(url: str) -> dict[str, str]:
    return {"Link": f'<{url}>; rel="next"'}


def make_client(session, frozen_time, **kwargs) -> GithubIssuesClient:
    return GithubIssuesClient(
        session,
        base_url=BASE_URL,
        sleep=kwargs.pop("sleep", MagicMock()),
        time_source=frozen_time,
        **kwargs,
    )


class TestIsRateLimited:
    @pytest.mark.parametrize(
        ("status_code", "headers", "expected"),
        [
            (429, {}, True),
            (429, {"X-RateLimit-Remaining": "500"}, True),
            (403, {"X-RateLimit-Remaining": "0"}, True),
            (403, {"X-RateLimit-Remaining": "17"}, False),
            (403, {}, False),
            (200, {}, False),
            (404, {}, False),
            (500, {}, False),
        ],
    )
    def test_detects_rate_limiting(self, make_response, status_code, headers, expected):
        response = make_response(status_code=status_code, headers=headers)

        assert _is_rate_limited(response) is expected

    def test_integer_remaining_header_is_not_rate_limited(self, make_response):
        """Documents the strict string comparison against ``"0"``."""
        response = make_response(status_code=403)
        response.headers["X-RateLimit-Remaining"] = 0

        assert _is_rate_limited(response) is False


class TestSecondsUntilRetry:
    def test_retry_after_takes_precedence_over_reset(self, make_response):
        response = make_response(
            headers={"Retry-After": "30", "X-RateLimit-Reset": "999999"}
        )

        assert _seconds_until_retry(response, attempt=1, now=1000.0) == 30.0

    def test_retry_after_zero_is_not_floored(self, make_response):
        """The 1.0s floor only applies to the ``X-RateLimit-Reset`` branch."""
        response = make_response(headers={"Retry-After": "0"})

        assert _seconds_until_retry(response, attempt=1, now=1000.0) == 0.0

    def test_uses_reset_header_relative_to_now(self, make_response):
        response = make_response(headers={"X-RateLimit-Reset": "1060"})

        assert _seconds_until_retry(response, attempt=1, now=1000.0) == 60.0

    @pytest.mark.parametrize("reset", ["990", "1000"])
    def test_reset_in_the_past_or_now_is_floored_to_one_second(
        self, make_response, reset
    ):
        response = make_response(headers={"X-RateLimit-Reset": reset})

        assert _seconds_until_retry(response, attempt=1, now=1000.0) == 1.0

    @pytest.mark.parametrize(
        ("attempt", "expected"),
        [(1, 2.0), (2, 4.0), (3, 8.0), (4, 16.0), (5, 32.0)],
    )
    def test_falls_back_to_exponential_backoff(self, make_response, attempt, expected):
        response = make_response()

        assert _seconds_until_retry(response, attempt=attempt, now=1000.0) == expected

    def test_non_numeric_retry_after_raises(self, make_response):
        """Documents R2: an HTTP-date ``Retry-After`` would blow up."""
        response = make_response(headers={"Retry-After": "soon"})

        with pytest.raises(ValueError, match="soon"):
            _seconds_until_retry(response, attempt=1, now=1000.0)


class TestGetWithBackoff:
    def test_returns_immediately_when_not_rate_limited(
        self, make_response, frozen_time
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(status_code=200)]
        sleep = MagicMock()
        client = make_client(session, frozen_time, sleep=sleep)

        response = client._get_with_backoff(ISSUES_URL, headers={})

        assert response.status_code == 200
        assert session.get.call_count == 1
        sleep.assert_not_called()

    def test_retries_until_a_non_rate_limited_response(
        self, make_response, frozen_time
    ):
        ok = make_response(status_code=200)
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [
            make_response(status_code=429),
            make_response(status_code=429),
            ok,
        ]
        sleep = MagicMock()
        client = make_client(session, frozen_time, sleep=sleep)

        response = client._get_with_backoff(ISSUES_URL, headers={})

        assert response is ok
        assert session.get.call_count == 3
        assert sleep.call_count == 2

    def test_stops_after_max_retries(self, make_response, frozen_time):
        """1 pre-loop request + 5 in-loop retries = 6 requests, 5 sleeps."""
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(status_code=429) for _ in range(7)]
        sleep = MagicMock()
        client = make_client(session, frozen_time, sleep=sleep)

        client._get_with_backoff(ISSUES_URL, headers={})

        assert session.get.call_count == 6
        assert sleep.call_count == 5

    def test_returns_the_rate_limited_response_without_raising(
        self, make_response, frozen_time
    ):
        """R1: exhausting retries yields the last 429, it does not raise."""
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(status_code=429) for _ in range(7)]
        client = make_client(session, frozen_time)

        response = client._get_with_backoff(ISSUES_URL, headers={})

        assert response.status_code == 429
        with pytest.raises(requests.HTTPError):
            response.raise_for_status()

    def test_sleeps_with_exponential_durations(self, make_response, frozen_time):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(status_code=429) for _ in range(7)]
        sleep = MagicMock()
        client = make_client(session, frozen_time, sleep=sleep)

        client._get_with_backoff(ISSUES_URL, headers={})

        assert sleep.call_args_list == [
            call(2.0),
            call(4.0),
            call(8.0),
            call(16.0),
            call(32.0),
        ]

    def test_honours_retry_after_header_on_every_sleep(
        self, make_response, frozen_time
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [
            make_response(status_code=429, headers={"Retry-After": "5"})
            for _ in range(7)
        ]
        sleep = MagicMock()
        client = make_client(session, frozen_time, sleep=sleep)

        client._get_with_backoff(ISSUES_URL, headers={})

        assert sleep.call_args_list == [call(5.0)] * 5

    def test_forwards_headers_params_and_timeout_on_every_attempt(
        self, make_response, frozen_time
    ):
        headers = {"Authorization": "Bearer test-token"}
        params = {"per_page": 100}
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [
            make_response(status_code=429),
            make_response(status_code=200),
        ]
        client = make_client(session, frozen_time)

        client._get_with_backoff(ISSUES_URL, headers=headers, params=params)

        assert (
            session.get.call_args_list
            == [
                call(
                    ISSUES_URL, headers=headers, params=params, timeout=DEFAULT_TIMEOUT
                )
            ]
            * 2
        )


class TestFetchIssues:
    def test_returns_validated_issues_from_a_single_page(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(json_body=make_issues_page(3))]
        client = make_client(session, frozen_time)

        issues = client.fetch_issues(issues_request)

        assert len(issues) == 3
        assert [issue.id for issue in issues] == [1, 2, 3]
        assert session.get.call_count == 1

    def test_builds_url_from_the_injected_base_url(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(json_body=[])]
        client = make_client(session, frozen_time)

        client.fetch_issues(issues_request)

        assert session.get.call_args.args[0] == ISSUES_URL

    def test_sends_the_expected_github_headers(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(json_body=[])]
        client = make_client(session, frozen_time)

        client.fetch_issues(issues_request)

        assert session.get.call_args.kwargs["headers"] == {
            "Authorization": "Bearer test-token",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def test_sends_per_page_on_the_first_request(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(json_body=[])]
        client = make_client(session, frozen_time)

        client.fetch_issues(issues_request)

        assert session.get.call_args.kwargs["params"] == {"per_page": 100}

    def test_follows_the_next_link_header(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [
            make_response(
                json_body=make_issues_page(2, start_id=1),
                headers=next_link(PAGE_TWO_URL),
            ),
            make_response(json_body=make_issues_page(2, start_id=3)),
        ]
        client = make_client(session, frozen_time)

        issues = client.fetch_issues(issues_request)

        assert len(issues) == 4
        assert session.get.call_count == 2
        assert session.get.call_args_list[1].args[0] == PAGE_TWO_URL

    def test_drops_params_on_paginated_requests(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [
            make_response(json_body=[], headers=next_link(PAGE_TWO_URL)),
            make_response(json_body=[]),
        ]
        client = make_client(session, frozen_time)

        client.fetch_issues(issues_request)

        assert session.get.call_args_list[1].kwargs["params"] is None

    def test_stops_when_link_header_has_no_next(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [
            make_response(
                json_body=make_issues_page(1),
                headers={"Link": f'<{ISSUES_URL}>; rel="prev"'},
            )
        ]
        client = make_client(session, frozen_time)

        issues = client.fetch_issues(issues_request)

        assert len(issues) == 1
        assert session.get.call_count == 1

    def test_returns_empty_list_for_an_empty_page(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(json_body=[])]
        client = make_client(session, frozen_time)

        assert client.fetch_issues(issues_request) == []

    def test_raises_and_logs_on_http_error(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(status_code=401)]
        client = make_client(session, frozen_time)

        with (
            structlog.testing.capture_logs() as logs,
            pytest.raises(requests.HTTPError),
        ):
            client.fetch_issues(issues_request)

        assert any(entry["log_level"] == "error" for entry in logs)

    def test_propagates_connection_errors(self, frozen_time, issues_request):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = requests.ConnectionError("boom")
        client = make_client(session, frozen_time)

        with pytest.raises(requests.ConnectionError, match="boom"):
            client.fetch_issues(issues_request)

    def test_validation_errors_are_not_swallowed(
        self, make_response, frozen_time, issues_request
    ):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(json_body=[{"id": 1}])]
        client = make_client(session, frozen_time)

        with pytest.raises(ValidationError):
            client.fetch_issues(issues_request)

    def test_discards_partial_pages_when_a_later_page_fails(
        self, make_response, frozen_time, issues_request
    ):
        """Documents the all-or-nothing behaviour: page 1 is lost too."""
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [
            make_response(
                json_body=make_issues_page(2), headers=next_link(PAGE_TWO_URL)
            ),
            make_response(status_code=500),
        ]
        client = make_client(session, frozen_time)

        with pytest.raises(requests.HTTPError):
            client.fetch_issues(issues_request)

    def test_stops_at_max_pages(self, make_response, frozen_time, issues_request):
        """A self-referencing ``next`` link must not loop forever."""
        session = MagicMock(spec=requests.Session)
        session.get.return_value = make_response(
            json_body=make_issues_page(1), headers=next_link(ISSUES_URL)
        )
        client = make_client(session, frozen_time, max_pages=1)

        issues = client.fetch_issues(issues_request)

        assert len(issues) == 1
        assert session.get.call_count == 1

    def test_parses_a_real_captured_payload(
        self, make_response, frozen_time, issues_request
    ):
        payload = [make_issue_payload()]
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [make_response(content=json.dumps(payload).encode())]
        client = make_client(session, frozen_time)

        issues = client.fetch_issues(issues_request)

        assert issues[0].pull_request is not None


class TestClientDefaults:
    def test_creates_a_real_session_when_none_is_given(self):
        client = GithubIssuesClient()

        assert isinstance(client._session, requests.Session)

    def test_strips_trailing_slash_from_base_url(self):
        client = GithubIssuesClient(base_url="https://fake.test/")

        assert client._base_url == "https://fake.test"
