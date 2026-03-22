from __future__ import annotations

import json

from app.schemas.review import CodeReviewAnalysis
from app.services.hf import HFService
from app.services.parsing import extract_json_payload


class HFReviewEngine:
    def __init__(self, hf: HFService) -> None:
        self.hf = hf

    async def review_diff(self, *, diff: str, pr_title: str, repo: str) -> CodeReviewAnalysis:
        prompt = {
            "task": "Review a raw git diff for code issues.",
            "pr_title": pr_title,
            "repo": repo,
            "diff": diff,
        }
        return await self._review(prompt)

    async def review_file(
        self,
        *,
        filename: str,
        content: str,
        pr_title: str,
        repo: str,
    ) -> CodeReviewAnalysis:
        prompt = {
            "task": "Review a single file for code issues.",
            "filename": filename,
            "pr_title": pr_title,
            "repo": repo,
            "content": content,
        }
        return await self._review(prompt)

    async def _review(self, payload: dict[str, str]) -> CodeReviewAnalysis:
        system_prompt = """
You are PRReviewIQ, a rigorous senior code reviewer.

Review only the code that is provided. Do not invent files, lines, or risks.
Allowed severities: Critical, Major, Minor, Suggestion.
Allowed categories: Security, Performance, Readability, Architecture, Testing, Bug.

Return JSON only using this shape:
{
  "summary": "short summary",
  "issues": [
    {
      "severity": "Critical|Major|Minor|Suggestion",
      "category": "Security|Performance|Readability|Architecture|Testing|Bug",
      "file": "path/to/file.py",
      "message": "short issue title",
      "explanation": "why this matters",
      "code_snippet": "exact code snippet from the provided content"
    }
  ],
  "standards": [
    {
      "rule": "reusable coding rule derived from the issue",
      "category": "Security|Performance|Readability|Architecture|Testing|Bug",
      "example": "short example from the reviewed code"
    }
  ]
}

Rules:
- Use exact code snippets from the provided code.
- Keep standards unique and reusable for future reviews.
- If there are no meaningful issues, return empty arrays.
- Never wrap the JSON in markdown fences.
""".strip()

        response_text = await self.hf.chat(
            system_prompt=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                }
            ],
            max_tokens=4096,
        )
        parsed = extract_json_payload(response_text)
        return CodeReviewAnalysis.model_validate(parsed)
