from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.schemas.review import (
    CodeReviewAnalysis,
    KnowledgeBaseState,
    NotionWriteResult,
    StandardRecord,
    WeeklyDigestResult,
)
from app.services.anthropic import AnthropicService
from app.services.mcp_client import MCPClientError, NotionMCPClient
from app.services.parsing import compact_json, extract_json_payload


class NotionAutomationError(RuntimeError):
    pass


class NotionService:
    def __init__(self, mcp_client: NotionMCPClient, anthropic: AnthropicService) -> None:
        self.mcp_client = mcp_client
        self.anthropic = anthropic

    async def close(self) -> None:
        await self.mcp_client.close()

    async def setup_workspace(self, parent_page_id: str) -> tuple[KnowledgeBaseState, list[str]]:
        today = date.today().isoformat()
        task = f"""
Set up a Notion knowledge base for PRReviewIQ under parent page ID `{parent_page_id}`.
Today's date is {today}.

Create or reuse these exact resources:
1. A database titled "🔍 Review Insights" with properties:
   - Title: title
   - Severity: select with options Critical, Major, Minor, Suggestion
   - Category: select with options Security, Performance, Readability, Architecture, Testing, Bug
   - File: rich_text
   - PR Title: rich_text
   - Repo: rich_text
   - Code Snippet: rich_text
   - Explanation: rich_text
   - Date: date
2. A database titled "📚 Coding Standards" with properties:
   - Rule: title
   - Category: select with options Security, Performance, Readability, Architecture, Testing, Bug
   - Example: rich_text
   - Auto-generated: checkbox
   - Times Flagged: number
   - Last Seen: date
3. A page titled "📊 Team Stats".

Avoid duplicates. Reuse exact-title matches if they already exist.

Return a final JSON result with this exact shape:
{{
  "review_insights_url": "https://...",
  "coding_standards_url": "https://...",
  "team_stats_url": "https://...",
  "activity": ["summary of what you created or reused"]
}}
""".strip()
        result, logs = await self._run_tool_loop(task, max_steps=20)
        state = KnowledgeBaseState(
            review_insights_url=result["review_insights_url"],
            coding_standards_url=result["coding_standards_url"],
            team_stats_url=result["team_stats_url"],
            parent_page_id=parent_page_id,
        )
        activity = result.get("activity", [])
        return state, [*logs, *activity]

    async def persist_review(
        self,
        *,
        analysis: CodeReviewAnalysis,
        pr_title: str,
        repo: str,
        state: KnowledgeBaseState,
    ) -> NotionWriteResult:
        today = date.today().isoformat()
        task = f"""
Use Notion MCP to write this PR review into the existing knowledge base.
Today's date is {today}.
Review Insights database URL: {state.review_insights_url}
Coding Standards database URL: {state.coding_standards_url}
PR title: {pr_title}
Repo: {repo}

Analysis JSON:
{analysis.model_dump_json(indent=2)}

Required actions:
- Create one Review Insights entry for each issue.
- Set the Title property to the issue message.
- Map Severity, Category, File, PR Title, Repo, Code Snippet, Explanation, and Date exactly.
- For each unique standard rule in the analysis, upsert it by exact Rule match in Coding Standards.
- If a rule already exists, increment Times Flagged by 1 and refresh Category, Example, Auto-generated, and Last Seen.
- If a rule does not exist, create it with Auto-generated=true, Times Flagged=1, and Last Seen=today.
- If there are no issues or no standards, do not create unnecessary pages.

Return a final JSON result with this exact shape:
{{
  "notion_url": "{state.review_insights_url}",
  "standards_updated": 0,
  "activity": ["what was created or updated"]
}}
""".strip()
        result, logs = await self._run_tool_loop(task, max_steps=30)
        return NotionWriteResult.model_validate(
            {
                "notion_url": result.get("notion_url", state.review_insights_url),
                "standards_updated": result.get("standards_updated", 0),
                "activity": [*logs, *result.get("activity", [])],
            }
        )

    async def fetch_standards(self, state: KnowledgeBaseState) -> tuple[list[StandardRecord], list[str]]:
        task = f"""
Read every entry from the Coding Standards database at this URL:
{state.coding_standards_url}

Return a final JSON result with this exact shape:
{{
  "rules": [
    {{
      "rule": "Rule text",
      "category": "Security|Performance|Readability|Architecture|Testing|Bug",
      "example": "Example text",
      "auto_generated": true,
      "times_flagged": 3,
      "last_seen": "YYYY-MM-DD or null",
      "url": "https://..."
    }}
  ],
  "activity": ["how you fetched the data"]
}}
Sort the rules by Times Flagged descending before returning them.
""".strip()
        result, logs = await self._run_tool_loop(task, max_steps=18)
        rules = [StandardRecord.model_validate(item) for item in result.get("rules", [])]
        return rules, [*logs, *result.get("activity", [])]

    async def create_weekly_digest(self, state: KnowledgeBaseState) -> WeeklyDigestResult:
        today = datetime.now(tz=UTC).date()
        current_week_start = today - timedelta(days=today.weekday())
        seven_days_ago = today - timedelta(days=7)
        fourteen_days_ago = today - timedelta(days=14)
        task = f"""
Create a weekly code quality digest using the existing Notion knowledge base.
Review Insights database URL: {state.review_insights_url}
Team Stats parent page URL: {state.team_stats_url}
Current date: {today.isoformat()}

You should:
- Read Review Insights entries from the last 7 days, starting {seven_days_ago.isoformat()}.
- If possible, compare against the previous 7-day period starting {fourteen_days_ago.isoformat()} to describe improvement trends.
- Group findings by category and severity.
- Identify the top recurring issues and most flagged files.
- Create a page under Team Stats titled "📊 Week of {current_week_start.isoformat()} Code Quality Report".
- Write sections for Overview, Category Breakdown, Severity Breakdown, Top Recurring Issues, Most Flagged Files, Improvement Trends, and 3 Specific Recommendations.

Return a final JSON result with this exact shape:
{{
  "report_title": "📊 Week of {current_week_start.isoformat()} Code Quality Report",
  "notion_url": "https://...",
  "summary": "1-2 sentence summary",
  "activity": ["what data you used and what page you created"]
}}
""".strip()
        result, logs = await self._run_tool_loop(task, max_steps=24)
        return WeeklyDigestResult.model_validate(
            {
                "report_title": result["report_title"],
                "notion_url": result["notion_url"],
                "summary": result["summary"],
                "activity": [*logs, *result.get("activity", [])],
            }
        )

    async def _run_tool_loop(self, task: str, *, max_steps: int) -> tuple[dict[str, Any], list[str]]:
        tool_catalog = await self.mcp_client.list_tools()
        rendered_tools = [
            {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "input_schema": tool.get("inputSchema", {}),
            }
            for tool in tool_catalog
        ]

        system_prompt = """
You are PRReviewIQ's Notion operator.
You have access to real Notion MCP tools, described in TOOL_CATALOG.

You must respond with exactly one JSON object and nothing else.

When you want to call a tool, respond with:
{
  "type": "tool_call",
  "name": "exact tool name from TOOL_CATALOG",
  "arguments": {},
  "comment": "short reason for this step"
}

When the task is complete, respond with:
{
  "type": "final",
  "result": { ...final JSON requested by the task... }
}

Rules:
- Use one tool call at a time.
- Use tool names exactly as listed.
- Arguments must follow the tool input schema.
- Prefer exact title matches and avoid duplicate resources.
- If a tool errors, revise the next call instead of repeating the same invalid request.
- Never return markdown fences.
""".strip()

        messages = [
            {
                "role": "user",
                "content": (
                    "TOOL_CATALOG:\n"
                    f"{json.dumps(rendered_tools, ensure_ascii=False, indent=2)}\n\n"
                    "TASK:\n"
                    f"{task}"
                ),
            }
        ]
        activity_log: list[str] = []

        for _ in range(max_steps):
            response_text = await self.anthropic.chat(
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=4096,
            )
            payload = extract_json_payload(response_text)
            action_type = payload.get("type")

            if action_type == "final":
                result = payload.get("result")
                if not isinstance(result, dict):
                    raise NotionAutomationError("Final result from Claude was not an object.")
                return result, activity_log

            if action_type != "tool_call":
                raise NotionAutomationError("Claude returned an invalid tool action payload.")

            tool_name = payload.get("name")
            tool_args = payload.get("arguments", {})
            if not isinstance(tool_args, dict):
                raise NotionAutomationError("Tool arguments must be a JSON object.")

            comment = payload.get("comment")
            if comment:
                activity_log.append(f"Claude: {comment}")

            try:
                tool_result = await self.mcp_client.call_tool(tool_name, tool_args)
                activity_log.append(self._render_tool_log(tool_name, tool_result))
                tool_feedback = {
                    "ok": True,
                    "tool_name": tool_name,
                    "tool_result": tool_result,
                }
            except MCPClientError as exc:
                tool_feedback = {
                    "ok": False,
                    "tool_name": tool_name,
                    "error": str(exc),
                }
                activity_log.append(f"{tool_name}: {exc}")

            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(payload, ensure_ascii=False),
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "TOOL_RESULT:\n"
                        f"{compact_json(tool_feedback)}\n\n"
                        "Continue with the next tool call or return the final result."
                    ),
                }
            )

        raise NotionAutomationError("Claude did not finish the Notion task within the tool loop limit.")

    @staticmethod
    def _render_tool_log(tool_name: str, tool_result: dict[str, Any]) -> str:
        url = _find_first_url(tool_result)
        if url:
            return f"{tool_name}: {url}"
        return f"{tool_name}: completed"


def _find_first_url(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "url" and isinstance(nested, str):
                return nested
            found = _find_first_url(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_first_url(item)
            if found:
                return found
    return None
