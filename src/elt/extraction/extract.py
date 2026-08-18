from elt.config.logging_configuration import log
from pydantic import TypeAdapter
import requests

from elt.extraction.models.fetch_issues_request_model import IssuesRequest
from elt.extraction.models.fetch_issues_response_model import Issue

issues_adapter = TypeAdapter(list[Issue])


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
    try:
        raw_response = requests.get(url, headers=headers)
        raw_response.raise_for_status()
        log.info("Data fetched")
        log.info(f"Status code: {raw_response.status_code}")
        log.info("Starting parsing")
        issues = issues_adapter.validate_json(raw_response.content)
        log.info(f"Parsed {len(issues)} issues")
        return issues
    except requests.exceptions.RequestException as e:
        log.error(e)
        raise