CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.github_issues
(
    url                        TEXT,
    repository_url             TEXT,
    labels_url                 TEXT,
    comments_url               TEXT,
    events_url                 TEXT,
    html_url                   TEXT,
    id                         BIGINT,
    node_id                    TEXT,
    number                     BIGINT,
    title                      TEXT,
    "user"                     JSONB,
    labels                     JSONB,
    state                      TEXT,
    locked                     BOOLEAN,
    assignees                  JSONB,
    milestone                  JSONB,
    comments                   BIGINT,
    created_at                 TIMESTAMP,
    updated_at                 TIMESTAMP,
    closed_at                  TIMESTAMP,
    assignee                   JSONB,
    author_association         TEXT,
    issue_field_values         JSONB,
    "type"                     JSONB,
    active_lock_reason         TEXT,
    draft                      BOOLEAN,
    pull_request               JSONB,
    body                       TEXT,
    closed_by                  JSONB,
    reactions                  JSONB,
    timeline_url               TEXT,
    performed_via_github_app   JSONB,
    state_reason               TEXT,
    pinned_comment             JSONB,
    sub_issues_summary         JSONB,
    issue_dependencies_summary JSONB,
    ingestion_date             DATE NOT NULL,
    _loaded_at                 TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_github_issues_partition
    ON raw.github_issues (ingestion_date);