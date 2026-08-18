import time

from elt.config.logging_configuration import log
from pydantic import TypeAdapter
import requests

from elt.extraction.models.fetch_issues_request_model import IssuesRequest
from elt.extraction.models.fetch_issues_response_model import Issue

issues_adapter = TypeAdapter(list[Issue])

MAX_RATE_LIMIT_RETRIES = 5


def _is_rate_limited(response: requests.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code == 403:
        return response.headers.get("X-RateLimit-Remaining") == "0"
    return False


def _seconds_until_retry(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        return float(retry_after)

    reset_at = response.headers.get("X-RateLimit-Reset")
    if reset_at is not None:
        return max(float(reset_at) - time.time(), 1.0)

    return float(2**attempt)


def _get_with_backoff(
    url: str, headers: dict, params: dict | None = None
) -> requests.Response:
    response = requests.get(url, headers=headers, params=params)
    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        if not _is_rate_limited(response):
            return response
        wait_seconds = _seconds_until_retry(response, attempt)
        log.warning(
            f"Rate limited by Github API (attempt {attempt}/{MAX_RATE_LIMIT_RETRIES}), "
            f"sleeping {wait_seconds:.1f}s before retrying"
        )
        time.sleep(wait_seconds)
        response = requests.get(url, headers=headers, params=params)
    return response


def fetch_issues(request: IssuesRequest) -> list[Issue]:
    log.info(
        f"Fetching Issues data from Github API for owner {request.owner} "
        f"and repo {request.repo}"
    )
    url = f"https://api.github.com/repos/{request.owner}/{request.repo}/issues"
    headers = {
        "Authorization": f"Bearer {request.api_key}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params = {"per_page": request.per_page}

    issues: list[Issue] = []
    page = 1
    try:
        while url:
            log.info(f"Fetching page {page}")
            raw_response = _get_with_backoff(url, headers=headers, params=params)
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
