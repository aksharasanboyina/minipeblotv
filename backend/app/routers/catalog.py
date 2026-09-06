import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_viewer_role
from app.core.database import get_db
from app.models import Episode
from app.services.placeholder_video import find_video_file, media_type_for
from app.services.storage import get_storage

router = APIRouter(tags=["catalog"])

# Every catalogue route is viewer-gated (Netflix-style login is real: no token,
# no browse/search/stream). Tokens come from POST /auth/viewer/token.


@router.get("/catalog")
async def get_catalogue(user: dict = Depends(require_viewer_role)):
    storage = get_storage()
    data = await storage.read_json("catalogues/catalogue.json")
    if not data:
        raise HTTPException(status_code=404, detail="No published catalogue available. Ask an admin to publish first.")
    return JSONResponse(content=data)


@router.get("/catalog/search")
async def search_catalogue(
    q: Optional[str] = None,
    category: Optional[str] = None,
    language: Optional[str] = None,
    section: Optional[str] = None,
    user: dict = Depends(require_viewer_role),
):
    storage = get_storage()
    data = await storage.read_json("catalogues/catalogue.json")
    if not data:
        raise HTTPException(status_code=404, detail="No published catalogue available.")

    results = []
    for sect in data.get("sections", []):
        if section and sect["section"] != section:
            continue

        for show in sect.get("shows", []):
            if category and category not in show.get("categories", []):
                continue

            q_lower = q.lower() if q else None
            # q matches show title, categories, synopsis AND episode titles/synopses
            # (per the API contract), so a show without a show-level match can still
            # appear when one of its episodes matches.
            show_matches_q = bool(q_lower) and (
                q_lower in show.get("title", "").lower()
                or any(q_lower in c.lower() for c in show.get("categories", []))
                or q_lower in show.get("synopsis", "").lower()
            )

            matched_seasons = []
            for season in show.get("seasons", []):
                matched_episodes = []
                for ep in season.get("episodes", []):
                    ep_matches = True
                    if q_lower:
                        ep_matches = (
                            q_lower in ep.get("title", "").lower()
                            or q_lower in ep.get("synopsis", "").lower()
                        )
                    if language and language not in ep.get("languages", []):
                        ep_matches = False
                    if ep_matches:
                        matched_episodes.append(ep)
                if matched_episodes:
                    matched_seasons.append({
                        "season_number": season["season_number"],
                        "episodes": matched_episodes,
                    })

            # Drop the show when a query/filter produced no episode matches, unless
            # the query itself matched the show (then the whole show is returned).
            if q_lower and not show_matches_q and not matched_seasons:
                continue
            if language and not q_lower and not matched_seasons:
                continue

            results.append({
                **show,
                "seasons": matched_seasons if matched_seasons else show.get("seasons", []),
                "section": sect["section"],
            })

    return {"results": results, "total": len(results)}


@router.get("/catalog/shows/{slug}")
async def get_show_detail(slug: str, user: dict = Depends(require_viewer_role)):
    storage = get_storage()
    data = await storage.read_json("catalogues/catalogue.json")
    if not data:
        raise HTTPException(status_code=404, detail="No published catalogue available.")

    for sect in data.get("sections", []):
        for show in sect.get("shows", []):
            if show.get("slug") == slug:
                return {**show, "section": sect["section"]}

    raise HTTPException(status_code=404, detail=f"Show '{slug}' not found in catalogue.")


@router.get("/catalog/video/{episode_id}")
async def stream_video(
    episode_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_viewer_role),
):
    """Stream a playable episode clip (Range-aware, so seeking works).

    The viewer's <video> element cannot send an Authorization header, so the token
    may also be passed as ?token=... (validated here exactly like the header).
    """
    try:
        ep_uuid = uuid.UUID(episode_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Episode not found")

    result = await db.execute(select(Episode).where(Episode.id == ep_uuid))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    path = find_video_file(episode.content_group)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="No video file is available for this episode yet.",
        )
    return FileResponse(
        path,
        media_type=media_type_for(path),
        headers={"Accept-Ranges": "bytes"},
    )
