from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GithubUser(BaseModel):
    login: str
    id: int
    node_id: str
    avatar_url: str
    gravatar_id: str
    url: str
    html_url: str
    followers_url: str
    following_url: str
    gists_url: str
    starred_url: str
    subscriptions_url: str
    organizations_url: str
    repos_url: str
    events_url: str
    received_events_url: str
    type: str
    user_view_type: str
    site_admin: bool


class Label(BaseModel):
    id: int
    node_id: str
    url: str
    name: str
    color: str
    default: bool
    description: str | None = None


class Milestone(BaseModel):
    url: str
    html_url: str
    labels_url: str
    id: int
    node_id: str
    number: int
    title: str
    description: str | None = None
    creator: GithubUser | None = None
    open_issues: int
    closed_issues: int
    state: Literal["open", "closed"]
    created_at: datetime
    updated_at: datetime
    due_on: datetime | None = None
    closed_at: datetime | None = None


class Reactions(BaseModel):
    url: str
    total_count: int
    thumbs_up: int = Field(alias="+1")
    thumbs_down: int = Field(alias="-1")
    laugh: int
    hooray: int
    confused: int
    heart: int
    rocket: int
    eyes: int


class PullRequestRef(BaseModel):
    url: str
    html_url: str
    diff_url: str
    patch_url: str
    merged_at: datetime | None = None


class SubIssuesSummary(BaseModel):
    total: int
    completed: int
    percent_completed: int


class IssueDependenciesSummary(BaseModel):
    blocked_by: int
    total_blocked_by: int
    blocking: int
    total_blocking: int


class IssueType(BaseModel):
    id: int
    node_id: str
    name: str
    description: str | None = None
    color: str | None = None
    created_at: datetime
    updated_at: datetime
    is_enabled: bool


class Issue(BaseModel):
    url: str
    repository_url: str
    labels_url: str
    comments_url: str
    events_url: str
    html_url: str
    id: int
    node_id: str
    number: int
    title: str
    user: GithubUser
    labels: list[Label]
    state: Literal["open", "closed"]
    locked: bool
    assignees: list[GithubUser]
    milestone: Milestone | None = None
    comments: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    assignee: GithubUser | None = None
    author_association: str
    issue_field_values: list
    type: IssueType | None = None
    active_lock_reason: str | None = None
    draft: bool | None = None
    pull_request: PullRequestRef | None = None
    body: str | None = None
    closed_by: GithubUser | None = None
    reactions: Reactions
    timeline_url: str
    performed_via_github_app: dict | None = None
    state_reason: str | None = None
    pinned_comment: str | None = None
    sub_issues_summary: SubIssuesSummary | None = None
    issue_dependencies_summary: IssueDependenciesSummary | None = None
