import asyncio

import pytest

from app.schemas.review import (
    CodeReviewAnalysis,
    CodingStandard,
    KnowledgeBaseState,
    NotionWriteResult,
    ReviewIssue,
    ReviewPRRequest,
    StandardRecord,
    WeeklyDigestResult,
)
from app.services.review import ReviewService, SetupRequiredError
from app.services.state import StateStore


class StubReviewer:
    async def review_diff(self, *, diff: str, pr_title: str, repo: str) -> CodeReviewAnalysis:
        return CodeReviewAnalysis(
            summary="One issue found.",
            issues=[
                ReviewIssue(
                    severity="Major",
                    category="Bug",
                    file="app/main.py",
                    message="Guard the empty diff path",
                    explanation="An empty diff should be handled before review.",
                    code_snippet="if not diff:\n    return",
                )
            ],
            standards=[
                CodingStandard(
                    rule="Handle empty review inputs explicitly.",
                    category="Bug",
                    example="if not diff: return",
                )
            ],
        )

    async def review_file(self, **kwargs) -> CodeReviewAnalysis:
        return await self.review_diff(diff="", pr_title="", repo="")


class StubNotionService:
    def __init__(self) -> None:
        self.persist_calls = []

    async def close(self) -> None:
        return None

    async def setup_workspace(self, parent_page_id: str):
        return (
            KnowledgeBaseState(
                review_insights_url="https://notion.so/review-insights",
                coding_standards_url="https://notion.so/coding-standards",
                team_stats_url="https://notion.so/team-stats",
                parent_page_id=parent_page_id,
            ),
            ["Created knowledge base."],
        )

    async def persist_review(self, *, analysis, pr_title: str, repo: str, state):
        self.persist_calls.append((analysis, pr_title, repo, state))
        return NotionWriteResult(
            notion_url=state.review_insights_url,
            standards_updated=1,
            activity=["Saved review insight."],
        )

    async def fetch_standards(self, state):
        return (
            [
                StandardRecord(
                    rule="Handle empty review inputs explicitly.",
                    category="Bug",
                    example="if not diff: return",
                    auto_generated=True,
                    times_flagged=4,
                    last_seen="2026-03-10",
                    url="https://notion.so/rule",
                )
            ],
            ["Fetched standards."],
        )

    async def create_weekly_digest(self, state):
        return WeeklyDigestResult(
            report_title="📊 Week of 2026-03-09 Code Quality Report",
            notion_url="https://notion.so/report",
            summary="Bug findings are down week over week.",
            activity=["Created weekly digest."],
        )


def test_review_requires_setup(tmp_path):
    service = ReviewService(
        reviewer=StubReviewer(),
        notion_service=StubNotionService(),
        state_store=StateStore(str(tmp_path / "state.json")),
        notion_parent_page_id="parent-page-id",
    )

    with pytest.raises(SetupRequiredError):
        asyncio.run(
            service.review_pr(
                ReviewPRRequest(
                    diff="diff --git a/app.py b/app.py",
                    pr_title="Test PR",
                    repo="demo-repo",
                )
            )
        )


def test_setup_and_review_flow(tmp_path):
    notion = StubNotionService()
    state_path = tmp_path / "state.json"
    service = ReviewService(
        reviewer=StubReviewer(),
        notion_service=notion,
        state_store=StateStore(str(state_path)),
        notion_parent_page_id="parent-page-id",
    )

    setup_response = asyncio.run(service.setup(force=True))
    review_response = asyncio.run(
        service.review_pr(
            ReviewPRRequest(
                diff="diff --git a/app.py b/app.py",
                pr_title="Test PR",
                repo="demo-repo",
            )
        )
    )
    standards_response = asyncio.run(service.get_standards())
    digest_response = asyncio.run(service.weekly_digest())

    assert state_path.exists()
    assert setup_response.review_insights_url == "https://notion.so/review-insights"
    assert review_response.standards_updated == 1
    assert review_response.issues[0].message == "Guard the empty diff path"
    assert notion.persist_calls[0][1] == "Test PR"
    assert standards_response.rules[0].times_flagged == 4
    assert digest_response.report_title == "📊 Week of 2026-03-09 Code Quality Report"
