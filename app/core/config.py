from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    hf_api_key: str = Field(..., alias="HF_API_KEY")
    hf_model: str = Field("Qwen/Qwen2.5-72B-Instruct", alias="HF_MODEL")
    notion_token: str = Field(..., alias="NOTION_TOKEN")
    notion_parent_page_id: str = Field(..., alias="NOTION_PARENT_PAGE_ID")
    notion_mcp_command: str = "npx"
    notion_mcp_package: str = "@notionhq/notion-mcp-server"
    notion_mcp_startup_timeout_seconds: float = 45.0
    notion_mcp_protocol_version: str = "2025-06-18"
    state_file: str = ".prreviewiq/state.json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
