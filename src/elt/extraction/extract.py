import time
from collections.abc import Callable

import requests
from pydantic import TypeAdapter

from elt.config.logging_configuration import log
from elt.extraction.models.fetch_issues_request_model import IssuesRequest
from elt.extraction.models.fetch_issues_response_model import Issue
from elt.ports import Sleeper

issues_adapter = TypeAdapter(list[Issue])

DEFAULT_BASE_URL = "https://api.github.com"
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_PAGES = 1000


def _is_rate_limited(response: requests.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code == 403:
        return response.headers.get("X-RateLimit-Remaining") == "0"
    return False


def _seconds_until_retry(
    response: requests.Response, attempt: int, now: float
) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        return float(retry_after)

    reset_at = response.headers.get("X-RateLimit-Reset")
    if reset_at is not None:
        return max(float(reset_at) - now, 1.0)

    return float(2**attempt)


class GithubIssuesClient:
    """GitHub Issues API client. Designed to be driven as an Airflow task."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        sleep: Sleeper = time.sleep,
        time_source: Callable[[], float] = time.time,
        max_rate_limit_retries: int = MAX_RATE_LIMIT_RETRIES,
        timeout: float = DEFAULT_TIMEOUT,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        self._session = session if session is not None else requests.Session()
        self._base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._time = time_source
        self._max_retries = max_rate_limit_retries
        self._timeout = timeout
        self._max_pages = max_pages

    def _get_with_backoff(
        self, url: str, headers: dict, params: dict | None = None
    ) -> requests.Response:
        response = self._session.get(
            url, headers=headers, params=params, timeout=self._timeout
        )
        for attempt in range(1, self._max_retries + 1):
            if not _is_rate_limited(response):
                return response
            wait_seconds = _seconds_until_retry(response, attempt, self._time())
            log.warning(
                f"Rate limited by Github API (attempt {attempt}/{self._max_retries}), "
                f"sleeping {wait_seconds:.1f}s before retrying"
            )
            self._sleep(wait_seconds)
            response = self._session.get(
                url, headers=headers, params=params, timeout=self._timeout
            )
        return response

    def fetch_issues(self, request: IssuesRequest) -> list[Issue]:
        log.info(
            f"Fetching Issues data from Github API for owner {request.owner} "
            f"and repo {request.repo}"
        )
        url = f"{self._base_url}/repos/{request.owner}/{request.repo}/issues"
        headers = {
            "Authorization": f"Bearer {request.api_key}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        params = {"per_page": request.per_page}

        issues: list[Issue] = []
        page = 1
        try:
            while url and page <= self._max_pages:
                log.info(f"Fetching page {page}")
                raw_response = self._get_with_backoff(
                    url, headers=headers, params=params
                )
                raw_response.raise_for_status()

                page_issues = issues_adapter.validate_json(raw_response.content)
                issues.extend(page_issues)
                log.info(f"Parsed {len(page_issues)} issues from page {page}")

                next_link = raw_response.links.get("next")
                url = next_link["url"] if next_link else None
                params = None
                page += 1
        except requests.exceptions.RequestException as e:
            log.error(e)
            raise

        log.info(f"Parsed {len(issues)} issues total across {page - 1} page(s)")
        return issues
