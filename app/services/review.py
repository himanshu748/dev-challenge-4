from __future__ import annotations

from app.schemas.review import (
    KnowledgeBaseState,
    ReviewFileRequest,
    ReviewPRRequest,
    ReviewResponse,
    SetupResponse,
    StandardRecord,
    StandardsResponse,
    WeeklyDigestResponse,
)
from app.services.notion import NotionService
from app.services.reviewer import HFReviewEngine
from app.services.state import StateStore


class SetupRequiredError(RuntimeError):
    pass


class ReviewService:
    def __init__(
        self,
        *,
        reviewer: HFReviewEngine,
        notion_service: NotionService,
        state_store: StateStore,
        notion_parent_page_id: str,
    ) -> None:
        self.reviewer = reviewer
        self.notion_service = notion_service
        self.state_store = state_store
        self.notion_parent_page_id = notion_parent_page_id

    async def close(self) -> None:
        await self.notion_service.close()

    async def setup(self, force: bool = False) -> SetupResponse:
        existing_state = self.state_store.load()
        if existing_state is not None and not force:
            return SetupResponse(
                **existing_state.model_dump(),
                logs=["Using existing cached Notion knowledge base. Pass force=true to rebuild it."],
            )

        state, logs = await self.notion_service.setup_workspace(self.notion_parent_page_id)
        self.state_store.save(state)
        return SetupResponse(**state.model_dump(), logs=logs)

    async def review_pr(self, request: ReviewPRRequest) -> ReviewResponse:
        state = self._require_state()
        analysis = await self.reviewer.review_diff(
            diff=request.diff,
            pr_title=request.pr_title,
            repo=request.repo,
        )
        notion_result = await self.notion_service.persist_review(
            analysis=analysis,
            pr_title=request.pr_title,
            repo=request.repo,
            state=state,
        )
        return ReviewResponse(
            issues=analysis.issues,
            notion_url=notion_result.notion_url,
            standards_updated=notion_result.standards_updated,
            logs=[f"AI found {len(analysis.issues)} issues.", *notion_result.activity],
        )

    async def review_file(self, request: ReviewFileRequest) -> ReviewResponse:
        state = self._require_state()
        analysis = await self.reviewer.review_file(
            filename=request.filename,
            content=request.content,
            pr_title=request.pr_title,
            repo=request.repo,
        )
        notion_result = await self.notion_service.persist_review(
            analysis=analysis,
            pr_title=request.pr_title,
            repo=request.repo,
            state=state,
        )
        return ReviewResponse(
            issues=analysis.issues,
            notion_url=notion_result.notion_url,
            standards_updated=notion_result.standards_updated,
            logs=[f"AI found {len(analysis.issues)} issues.", *notion_result.activity],
        )

    async def get_standards(self) -> StandardsResponse:
        state = self._require_state()
        rules, logs = await self.notion_service.fetch_standards(state)
        return StandardsResponse(rules=rules, logs=logs)

    async def weekly_digest(self) -> WeeklyDigestResponse:
        state = self._require_state()
        digest = await self.notion_service.create_weekly_digest(state)
        return WeeklyDigestResponse(
            report_title=digest.report_title,
            notion_url=digest.notion_url,
            summary=digest.summary,
            logs=digest.activity,
        )

    def _require_state(self) -> KnowledgeBaseState:
        state = self.state_store.load()
        if state is None:
            raise SetupRequiredError("Run POST /api/setup before using review or digest endpoints.")
        return state
