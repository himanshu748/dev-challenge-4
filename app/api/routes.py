from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from app.dependencies import get_review_service
from app.schemas.review import (
    ReviewFileRequest,
    ReviewGitHubPRRequest,
    ReviewPRRequest,
    ReviewResponse,
    SetupRequest,
    SetupResponse,
    StandardsResponse,
    WeeklyDigestResponse,
)
from app.services.review import ReviewService, SetupRequiredError

router = APIRouter()
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@router.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/setup", response_model=SetupResponse)
async def setup(
    payload: SetupRequest | None = None,
    service: ReviewService = Depends(get_review_service),
) -> SetupResponse:
    return await _wrap_errors(service.setup((payload or SetupRequest()).force))


@router.post("/api/review-pr", response_model=ReviewResponse)
async def review_pr(
    payload: ReviewPRRequest,
    service: ReviewService = Depends(get_review_service),
) -> ReviewResponse:
    return await _wrap_errors(service.review_pr(payload))


@router.post("/api/review-github-pr", response_model=ReviewResponse)
async def review_github_pr(
    payload: ReviewGitHubPRRequest,
    service: ReviewService = Depends(get_review_service),
) -> ReviewResponse:
    return await _wrap_errors(service.review_github_pr(payload))


@router.post("/api/review-file", response_model=ReviewResponse)
async def review_file(
    payload: ReviewFileRequest,
    service: ReviewService = Depends(get_review_service),
) -> ReviewResponse:
    return await _wrap_errors(service.review_file(payload))


@router.get("/api/standards", response_model=StandardsResponse)
async def standards(
    service: ReviewService = Depends(get_review_service),
) -> StandardsResponse:
    return await _wrap_errors(service.get_standards())


@router.post("/api/weekly-digest", response_model=WeeklyDigestResponse)
async def weekly_digest(
    service: ReviewService = Depends(get_review_service),
) -> WeeklyDigestResponse:
    return await _wrap_errors(service.weekly_digest())


async def _wrap_errors(coro):
    try:
        return await coro
    except SetupRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
