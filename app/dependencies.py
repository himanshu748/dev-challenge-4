from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.anthropic import AnthropicService
from app.services.mcp_client import NotionMCPClient
from app.services.notion import NotionService
from app.services.review import ReviewService
from app.services.reviewer import ClaudeReviewEngine
from app.services.state import StateStore


@lru_cache
def get_state_store() -> StateStore:
    settings = get_settings()
    return StateStore(settings.state_file)


@lru_cache
def get_anthropic_service() -> AnthropicService:
    settings = get_settings()
    return AnthropicService(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        api_url=settings.anthropic_api_url,
        version=settings.anthropic_version,
    )


@lru_cache
def get_notion_mcp_client() -> NotionMCPClient:
    settings = get_settings()
    return NotionMCPClient(settings)


@lru_cache
def get_reviewer() -> ClaudeReviewEngine:
    return ClaudeReviewEngine(get_anthropic_service())


@lru_cache
def get_notion_service() -> NotionService:
    return NotionService(
        mcp_client=get_notion_mcp_client(),
        anthropic=get_anthropic_service(),
    )


@lru_cache
def get_review_service() -> ReviewService:
    settings: Settings = get_settings()
    return ReviewService(
        reviewer=get_reviewer(),
        notion_service=get_notion_service(),
        state_store=get_state_store(),
        notion_parent_page_id=settings.notion_parent_page_id,
    )
