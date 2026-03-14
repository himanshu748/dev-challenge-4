from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["Critical", "Major", "Minor", "Suggestion"]
Category = Literal["Security", "Performance", "Readability", "Architecture", "Testing", "Bug"]


class SetupRequest(BaseModel):
    force: bool = False


class ReviewPRRequest(BaseModel):
    diff: str
    pr_title: str
    repo: str


class ReviewFileRequest(BaseModel):
    filename: str
    content: str
    pr_title: str
    repo: str


class ReviewIssue(BaseModel):
    severity: Severity
    category: Category
    file: str
    message: str
    explanation: str
    code_snippet: str


class CodingStandard(BaseModel):
    rule: str
    category: Category
    example: str


class StandardRecord(CodingStandard):
    auto_generated: bool = True
    times_flagged: int = 0
    last_seen: str | None = None
    url: str | None = None


class CodeReviewAnalysis(BaseModel):
    summary: str = "No issues found."
    issues: list[ReviewIssue] = Field(default_factory=list)
    standards: list[CodingStandard] = Field(default_factory=list)


class KnowledgeBaseState(BaseModel):
    review_insights_url: str
    coding_standards_url: str
    team_stats_url: str
    parent_page_id: str


class SetupResponse(KnowledgeBaseState):
    logs: list[str] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    issues: list[ReviewIssue] = Field(default_factory=list)
    notion_url: str
    standards_updated: int = 0
    logs: list[str] = Field(default_factory=list)


class StandardsResponse(BaseModel):
    rules: list[StandardRecord] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)


class WeeklyDigestResponse(BaseModel):
    report_title: str
    notion_url: str
    summary: str
    logs: list[str] = Field(default_factory=list)


class NotionWriteResult(BaseModel):
    notion_url: str
    standards_updated: int = 0
    activity: list[str] = Field(default_factory=list)


class WeeklyDigestResult(BaseModel):
    report_title: str
    notion_url: str
    summary: str
    activity: list[str] = Field(default_factory=list)
