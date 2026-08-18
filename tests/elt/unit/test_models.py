"""Unit tests for the Pydantic request/response models."""

import json
from datetime import datetime

import pytest
from factories import base_page, make_issue, make_issue_payload
from pydantic import ValidationError

from elt.extraction.models.fetch_issues_request_model import IssuesRequest
from elt.extraction.models.fetch_issues_response_model import Issue, Reactions


class TestReactions:
    def test_validates_from_api_aliases(self):
        reactions = Reactions.model_validate(
            {
                "url": "https://fake.test/reactions",
                "total_count": 7,
                "+1": 5,
                "-1": 2,
                "laugh": 0,
                "hooray": 0,
                "confused": 0,
                "heart": 0,
                "rocket": 0,
                "eyes": 0,
            }
        )

        assert reactions.thumbs_up == 5
        assert reactions.thumbs_down == 2

    def test_rejects_field_names_instead_of_aliases(self):
        with pytest.raises(ValidationError, match=r"\+1"):
            Reactions(
                url="https://fake.test/reactions",
                total_count=7,
                thumbs_up=5,
                thumbs_down=2,
                laugh=0,
                hooray=0,
                confused=0,
                heart=0,
                rocket=0,
                eyes=0,
            )

    def test_dump_emits_field_names_not_aliases(self):
        """Pins the Parquet column names for the reactions struct."""
        dumped = make_issue().reactions.model_dump(mode="json")

        assert "thumbs_up" in dumped
        assert "thumbs_down" in dumped
        assert "+1" not in dumped
        assert "-1" not in dumped


class TestIssuesRequest:
    @pytest.mark.parametrize("per_page", [1, 50, 100])
    def test_accepts_valid_per_page(self, per_page):
        request = IssuesRequest(
            owner="octo", repo="hello", api_key="t", per_page=per_page
        )

        assert request.per_page == per_page

    @pytest.mark.parametrize(
        ("per_page", "message"),
        [
            (0, "greater than or equal to 1"),
            (-5, "greater than or equal to 1"),
            (101, "less than or equal to 100"),
        ],
    )
    def test_rejects_out_of_range_per_page(self, per_page, message):
        with pytest.raises(ValidationError, match=message):
            IssuesRequest(owner="octo", repo="hello", api_key="t", per_page=per_page)

    def test_per_page_defaults_to_100(self):
        assert IssuesRequest(owner="octo", repo="hello", api_key="t").per_page == 100

    @pytest.mark.parametrize("missing", ["owner", "repo", "api_key"])
    def test_requires_core_fields(self, missing):
        kwargs = {"owner": "octo", "repo": "hello", "api_key": "t"}
        del kwargs[missing]

        with pytest.raises(ValidationError, match=missing):
            IssuesRequest(**kwargs)


class TestIssue:
    def test_parses_the_captured_page(self):
        page = base_page()

        issues = [Issue.model_validate(payload) for payload in page]

        assert len(issues) == 2
        assert issues[0].pull_request is not None
        assert issues[0].draft is False
        assert issues[1].pull_request is None
        assert issues[1].milestone is None

    def test_round_trips_through_json_dump_by_alias(self):
        issue = make_issue()

        restored = Issue.model_validate(
            json.loads(json.dumps(issue.model_dump(mode="json", by_alias=True)))
        )

        assert restored.id == issue.id
        assert restored.title == issue.title
        assert restored.reactions.thumbs_up == issue.reactions.thumbs_up

    def test_default_json_dump_is_not_re_validatable(self):
        """Documents the alias asymmetry the Parquet schema depends on.

        ``model_dump(mode="json")`` emits ``thumbs_up``/``thumbs_down`` (what
        lands in Parquet), which the model itself refuses to read back because
        ``populate_by_name`` is off.
        """
        dumped = make_issue().model_dump(mode="json")

        with pytest.raises(ValidationError, match=r"\+1"):
            Issue.model_validate(dumped)

    @pytest.mark.parametrize(
        "field",
        [
            "milestone",
            "type",
            "pull_request",
            "closed_by",
            "sub_issues_summary",
            "issue_dependencies_summary",
            "draft",
            "body",
            "state_reason",
            "pinned_comment",
            "active_lock_reason",
            "performed_via_github_app",
        ],
    )
    def test_optional_fields_default_to_none(self, field):
        payload = make_issue_payload()
        payload.pop(field, None)

        issue = Issue.model_validate(payload)

        assert getattr(issue, field) is None

    @pytest.mark.parametrize(
        "field",
        ["reactions", "user", "issue_field_values", "id", "state"],
    )
    def test_required_fields_are_mandatory(self, field):
        payload = make_issue_payload()
        del payload[field]

        with pytest.raises(ValidationError, match=field):
            Issue.model_validate(payload)

    @pytest.mark.parametrize("state", ["open", "closed"])
    def test_accepts_known_states(self, state):
        assert Issue.model_validate(make_issue_payload(state=state)).state == state

    def test_rejects_unknown_state(self):
        with pytest.raises(ValidationError, match="state"):
            Issue.model_validate(make_issue_payload(state="merged"))

    def test_created_at_dumps_as_parseable_string(self):
        """Pins that the Parquet column is a string, not a timestamp."""
        dumped = make_issue().model_dump(mode="json")

        assert isinstance(dumped["created_at"], str)
        assert isinstance(datetime.fromisoformat(dumped["created_at"]), datetime)

    def test_json_dump_is_serialisable(self):
        """Precondition of ``pa.Table.from_pylist``."""
        assert json.dumps(make_issue().model_dump(mode="json"))
