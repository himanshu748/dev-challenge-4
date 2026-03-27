from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.schemas.review import (
    CodeReviewAnalysis,
    KnowledgeBaseState,
    NotionWriteResult,
    StandardRecord,
    WeeklyDigestResult,
)
from app.services.hf import HFService
from app.services.mcp_client import (
    MCPClientError,
    _bullet,
    _heading,
    _para,
    _rt,
    extract_date,
    extract_id_from_url,
    extract_number,
    extract_rich_text,
    extract_select,
    extract_checkbox,
    extract_title,
    find_by_title,
    mcp_create_database,
    mcp_create_db_page,
    mcp_create_page,
    mcp_patch_page,
    mcp_query_database,
    mcp_search,
    notion_session,
)
from app.services.parsing import extract_json_payload


class NotionAutomationError(RuntimeError):
    pass


DIGEST_SYSTEM_PROMPT = """
You are PRReviewIQ's digest generator.
Given a list of code review issues from the past week, generate a weekly digest in JSON:
{
  "summary": "1-2 sentence overview",
  "overview": "paragraph summarizing the week's code quality",
  "categories": {"Security": 2, "Performance": 1},
  "severities": {"Critical": 1, "Major": 3},
  "top_issues": ["most common issue 1", "most common issue 2"],
  "most_flagged_files": ["file1.py", "file2.js"],
  "trends": "paragraph about improvement or regression trends",
  "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"]
}
If there are no issues, still provide a positive summary and recommendations.
Never wrap the JSON in markdown fences.
""".strip()


class NotionService:
    def __init__(self, settings: Settings, hf: HFService) -> None:
        self.settings = settings
        self.hf = hf

    async def close(self) -> None:
        pass  # no persistent connection; sessions are opened per-operation

    # ─── setup_workspace ─────────────────────────────────────────────────

    async def setup_workspace(
        self, parent_page_id: str
    ) -> tuple[KnowledgeBaseState, list[str]]:
        logs: list[str] = []

        async with notion_session(self.settings) as session:
            existing = await mcp_search(session, "")

            # ── Review Insights database ─────────────────────────────────
            review_db = find_by_title(existing, "🔍 Review Insights")
            if review_db is None:
                review_db = await mcp_create_database(
                    session,
                    parent_page_id,
                    "🔍 Review Insights",
                    token=self.settings.notion_token,
                    properties={
                        "Title": {"title": {}},
                        "Severity": {
                            "select": {
                                "options": [
                                    {"name": "Critical"},
                                    {"name": "Major"},
                                    {"name": "Minor"},
                                    {"name": "Suggestion"},
                                ]
                            }
                        },
                        "Category": {
                            "select": {
                                "options": [
                                    {"name": "Security"},
                                    {"name": "Performance"},
                                    {"name": "Readability"},
                                    {"name": "Architecture"},
                                    {"name": "Testing"},
                                    {"name": "Bug"},
                                ]
                            }
                        },
                        "File": {"rich_text": {}},
                        "PR Title": {"rich_text": {}},
                        "Repo": {"rich_text": {}},
                        "Code Snippet": {"rich_text": {}},
                        "Explanation": {"rich_text": {}},
                        "Date": {"date": {}},
                    },
                )
                logs.append("Created 🔍 Review Insights database")
            else:
                logs.append("Reused existing 🔍 Review Insights database")

            # ── Coding Standards database ────────────────────────────────
            standards_db = find_by_title(existing, "📚 Coding Standards")
            if standards_db is None:
                standards_db = await mcp_create_database(
                    session,
                    parent_page_id,
                    "📚 Coding Standards",
                    token=self.settings.notion_token,
                    properties={
                        "Rule": {"title": {}},
                        "Category": {
                            "select": {
                                "options": [
                                    {"name": "Security"},
                                    {"name": "Performance"},
                                    {"name": "Readability"},
                                    {"name": "Architecture"},
                                    {"name": "Testing"},
                                    {"name": "Bug"},
                                ]
                            }
                        },
                        "Example": {"rich_text": {}},
                        "Auto-generated": {"checkbox": {}},
                        "Times Flagged": {"number": {}},
                        "Last Seen": {"date": {}},
                    },
                )
                logs.append("Created 📚 Coding Standards database")
            else:
                logs.append("Reused existing 📚 Coding Standards database")

            # ── Team Stats page ──────────────────────────────────────────
            team_stats = find_by_title(existing, "📊 Team Stats")
            if team_stats is None:
                team_stats = await mcp_create_page(
                    session,
                    parent_page_id,
                    "📊 Team Stats",
                    [_para("Team code quality statistics and weekly digests.")],
                )
                logs.append("Created 📊 Team Stats page")
            else:
                logs.append("Reused existing 📊 Team Stats page")

        state = KnowledgeBaseState(
            review_insights_url=review_db.get("url", ""),
            coding_standards_url=standards_db.get("url", ""),
            team_stats_url=team_stats.get("url", ""),
            parent_page_id=parent_page_id,
        )
        return state, logs

    # ─── persist_review ──────────────────────────────────────────────────

    async def persist_review(
        self,
        *,
        analysis: CodeReviewAnalysis,
        pr_title: str,
        repo: str,
        state: KnowledgeBaseState,
    ) -> NotionWriteResult:
        today = date.today().isoformat()
        logs: list[str] = []
        standards_updated = 0

        review_db_id = extract_id_from_url(state.review_insights_url)
        standards_db_id = extract_id_from_url(state.coding_standards_url)

        async with notion_session(self.settings) as session:
            # ── Create Review Insights entries ────────────────────────────
            for issue in analysis.issues:
                await mcp_create_db_page(
                    session,
                    review_db_id,
                    {
                        "Title": {"title": _rt(issue.message)},
                        "Severity": {"select": {"name": issue.severity}},
                        "Category": {"select": {"name": issue.category}},
                        "File": {"rich_text": _rt(issue.file)},
                        "PR Title": {"rich_text": _rt(pr_title)},
                        "Repo": {"rich_text": _rt(repo)},
                        "Code Snippet": {"rich_text": _rt(issue.code_snippet)},
                        "Explanation": {"rich_text": _rt(issue.explanation)},
                        "Date": {"date": {"start": today}},
                    },
                )
                logs.append(f"Created review insight: {issue.message}")

            # ── Upsert Coding Standards ──────────────────────────────────
            for standard in analysis.standards:
                existing_pages = await mcp_query_database(
                    session,
                    standards_db_id,
                    filter_obj={
                        "property": "Rule",
                        "title": {"equals": standard.rule},
                    },
                    token=self.settings.notion_token,
                )

                if existing_pages:
                    page = existing_pages[0]
                    page_id = page["id"]
                    current_count = extract_number(
                        page.get("properties", {}).get("Times Flagged", {})
                    )
                    await mcp_patch_page(
                        session,
                        page_id,
                        {
                            "Category": {"select": {"name": standard.category}},
                            "Example": {"rich_text": _rt(standard.example)},
                            "Auto-generated": {"checkbox": True},
                            "Times Flagged": {"number": current_count + 1},
                            "Last Seen": {"date": {"start": today}},
                        },
                    )
                    logs.append(f"Updated standard: {standard.rule}")
                else:
                    await mcp_create_db_page(
                        session,
                        standards_db_id,
                        {
                            "Rule": {"title": _rt(standard.rule)},
                            "Category": {"select": {"name": standard.category}},
                            "Example": {"rich_text": _rt(standard.example)},
                            "Auto-generated": {"checkbox": True},
                            "Times Flagged": {"number": 1},
                            "Last Seen": {"date": {"start": today}},
                        },
                    )
                    logs.append(f"Created standard: {standard.rule}")
                standards_updated += 1

        return NotionWriteResult(
            notion_url=state.review_insights_url,
            standards_updated=standards_updated,
            activity=logs,
        )

    # ─── fetch_standards ─────────────────────────────────────────────────

    async def fetch_standards(
        self, state: KnowledgeBaseState
    ) -> tuple[list[StandardRecord], list[str]]:
        standards_db_id = extract_id_from_url(state.coding_standards_url)
        logs: list[str] = []

        async with notion_session(self.settings) as session:
            pages = await mcp_query_database(
                session,
                standards_db_id,
                sorts=[{"property": "Times Flagged", "direction": "descending"}],
                token=self.settings.notion_token,
            )
            logs.append(f"Fetched {len(pages)} coding standards")

        rules: list[StandardRecord] = []
        for page in pages:
            props = page.get("properties", {})
            rule = extract_title(props.get("Rule", {}))
            if not rule:
                continue
            category = extract_select(props.get("Category", {}))
            rules.append(
                StandardRecord(
                    rule=rule,
                    category=category or "Readability",
                    example=extract_rich_text(props.get("Example", {})),
                    auto_generated=extract_checkbox(props.get("Auto-generated", {})),
                    times_flagged=extract_number(props.get("Times Flagged", {})),
                    last_seen=extract_date(props.get("Last Seen", {})),
                    url=page.get("url"),
                )
            )

        return rules, logs

    # ─── create_weekly_digest ────────────────────────────────────────────

    async def create_weekly_digest(
        self, state: KnowledgeBaseState
    ) -> WeeklyDigestResult:
        today = datetime.now(tz=UTC).date()
        current_week_start = today - timedelta(days=today.weekday())
        seven_days_ago = today - timedelta(days=7)

        review_db_id = extract_id_from_url(state.review_insights_url)
        team_stats_id = extract_id_from_url(state.team_stats_url)
        logs: list[str] = []

        async with notion_session(self.settings) as session:
            # ── Read recent review insights ──────────────────────────────
            recent_pages = await mcp_query_database(
                session,
                review_db_id,
                filter_obj={
                    "property": "Date",
                    "date": {"on_or_after": seven_days_ago.isoformat()},
                },
                token=self.settings.notion_token,
            )
            logs.append(f"Read {len(recent_pages)} review insights from last 7 days")

            # ── Summarise for HF ─────────────────────────────────────────
            issues_summary: list[dict[str, str]] = []
            for page in recent_pages:
                props = page.get("properties", {})
                issues_summary.append(
                    {
                        "message": extract_title(props.get("Title", {})),
                        "severity": extract_select(props.get("Severity", {})),
                        "category": extract_select(props.get("Category", {})),
                        "file": extract_rich_text(props.get("File", {})),
                    }
                )

            # ── Generate digest via HF ───────────────────────────────────
            digest_text = await self.hf.chat(
                system_prompt=DIGEST_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "week_start": current_week_start.isoformat(),
                                "issues": issues_summary,
                            },
                            ensure_ascii=False,
                        ),
                    }
                ],
                max_tokens=4096,
            )
            digest = extract_json_payload(digest_text)

            # ── Build Notion blocks ──────────────────────────────────────
            report_title = (
                f"📊 Week of {current_week_start.isoformat()} Code Quality Report"
            )
            blocks = _build_digest_blocks(digest)

            # ── Write page under Team Stats ──────────────────────────────
            page = await mcp_create_page(
                session, team_stats_id, report_title, blocks
            )
            logs.append(f"Created digest page: {report_title}")

        return WeeklyDigestResult(
            report_title=report_title,
            notion_url=page.get("url", ""),
            summary=digest.get("summary", ""),
            activity=logs,
        )


# ─── Private helpers ─────────────────────────────────────────────────────────


def _build_digest_blocks(digest: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Notion page blocks from a digest JSON payload."""
    blocks: list[dict[str, Any]] = []

    blocks.append(_heading("Overview"))
    blocks.append(_para(digest.get("overview", "No data available.")))

    blocks.append(_heading("Category Breakdown"))
    for cat, count in digest.get("categories", {}).items():
        blocks.append(_bullet(f"{cat}: {count} issues"))

    blocks.append(_heading("Severity Breakdown"))
    for sev, count in digest.get("severities", {}).items():
        blocks.append(_bullet(f"{sev}: {count} issues"))

    blocks.append(_heading("Top Recurring Issues"))
    for issue in digest.get("top_issues", []):
        blocks.append(_bullet(issue))

    blocks.append(_heading("Most Flagged Files"))
    for f in digest.get("most_flagged_files", []):
        blocks.append(_bullet(f))

    blocks.append(_heading("Improvement Trends"))
    blocks.append(_para(digest.get("trends", "No trends data.")))

    blocks.append(_heading("Recommendations"))
    for rec in digest.get("recommendations", []):
        blocks.append(_bullet(rec))

    return blocks
