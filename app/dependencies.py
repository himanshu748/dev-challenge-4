from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.hf import HFService
from app.services.notion import NotionService
from app.services.review import ReviewService
from app.services.reviewer import HFReviewEngine
from app.services.state import StateStore


@lru_cache
def get_state_store() -> StateStore:
    settings = get_settings()
    return StateStore(settings.state_file)


@lru_cache
def get_hf_service() -> HFService:
    settings = get_settings()
    return HFService(
        api_key=settings.hf_api_key,
        model=settings.hf_model,
    )


@lru_cache
def get_reviewer() -> HFReviewEngine:
    return HFReviewEngine(get_hf_service())


@lru_cache
def get_notion_service() -> NotionService:
    return NotionService(
        settings=get_settings(),
        hf=get_hf_service(),
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
