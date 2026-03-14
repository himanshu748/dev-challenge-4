from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-sonnet-4-20250514", alias="ANTHROPIC_MODEL")
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_version: str = "2023-06-01"
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
