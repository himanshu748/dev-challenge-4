from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.dependencies import get_hf_service, get_review_service

app = FastAPI(title="PRReviewIQ", version="0.1.0")
app.include_router(router)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parent / "static"),
    name="static",
)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await get_review_service().close()
    await get_hf_service().close()
