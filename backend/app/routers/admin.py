import os
import uuid
from math import ceil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_role
from app.core.config import settings
from app.core.database import get_db
from app.models import Artwork, Episode, PublishRun, PublishStatus, Season, Show
from app.schemas.schemas import (
    ArtworkResponse,
    EpisodeCreate,
    EpisodeResponse,
    EpisodeUpdate,
    PublishRunResponse,
    SeasonCreate,
    SeasonResponse,
    ShowCreate,
    ShowResponse,
    ShowUpdate,
    ValidationReport,
)
from app.services.artwork import ALLOWED_TYPES, validate_artwork
from app.services.placeholder_video import (
    ALLOWED_VIDEO_EXTENSIONS,
    delete_video_file,
    find_video_file,
    probe_video_file,
)
from app.services.publish import get_validation_issues, publish_catalogue
from app.services.storage import get_storage

router = APIRouter(prefix="/admin", tags=["admin"])


# ---- Shows ----
@router.get("/shows", response_model=dict)
async def list_shows(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    section: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    query = select(Show)
    count_query = select(func.count(Show.id))

    if section:
        query = query.where(Show.section == section)
        count_query = count_query.where(Show.section == section)
    if status_filter:
        query = query.where(Show.status == status_filter)
        count_query = count_query.where(Show.status == status_filter)
    if search:
        q = f"%{search}%"
        query = query.where(Show.title.ilike(q))
        count_query = count_query.where(Show.title.ilike(q))

    total = (await db.execute(count_query)).scalar() or 0
    total_pages = max(1, ceil(total / page_size))

    query = query.order_by(Show.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    shows = result.scalars().all()

    return {
        "items": [ShowResponse.model_validate(s).model_dump(mode="json") for s in shows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.post("/shows", response_model=ShowResponse, status_code=201)
async def create_show(
    data: ShowCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    existing = await db.execute(select(Show).where(Show.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"A show with slug '{data.slug}' already exists.")

    show = Show(
        title=data.title,
        slug=data.slug,
        section=data.section,
        categories=data.categories,
        synopsis=data.synopsis,
        status=PublishStatus(data.status),
    )
    db.add(show)
    await db.flush()
    await db.refresh(show)
    return ShowResponse.model_validate(show)


@router.get("/shows/{show_id}", response_model=ShowResponse)
async def get_show(
    show_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    result = await db.execute(select(Show).where(Show.id == show_id))
    show = result.scalar_one_or_none()
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    return ShowResponse.model_validate(show)


@router.put("/shows/{show_id}", response_model=ShowResponse)
async def update_show(
    show_id: str,
    data: ShowUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    result = await db.execute(select(Show).where(Show.id == show_id))
    show = result.scalar_one_or_none()
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")

    update_data = data.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = PublishStatus(update_data["status"])
    for key, value in update_data.items():
        setattr(show, key, value)

    await db.flush()
    await db.refresh(show)
    return ShowResponse.model_validate(show)


@router.delete("/shows/{show_id}", status_code=204)
async def delete_show(
    show_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    result = await db.execute(select(Show).where(Show.id == show_id))
    show = result.scalar_one_or_none()
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    await db.delete(show)
    await db.flush()


# ---- Seasons ----
@router.get("/shows/{show_id}/seasons", response_model=list)
async def list_seasons(
    show_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    result = await db.execute(
        select(Season).where(Season.show_id == show_id).order_by(Season.season_number)
    )
    seasons = result.scalars().all()
    return [SeasonResponse.model_validate(s).model_dump(mode="json") for s in seasons]


@router.post("/shows/{show_id}/seasons", response_model=SeasonResponse, status_code=201)
async def create_season(
    show_id: str,
    data: SeasonCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    show_result = await db.execute(select(Show).where(Show.id == show_id))
    if not show_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Show not found")

    existing = await db.execute(
        select(Season).where(Season.show_id == show_id, Season.season_number == data.season_number)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Season {data.season_number} already exists for this show.")

    season = Season(show_id=show_id, season_number=data.season_number)
    db.add(season)
    await db.flush()
    await db.refresh(season)
    return SeasonResponse.model_validate(season)


# ---- Episodes ----
@router.get("/seasons/{season_id}/episodes", response_model=dict)
async def list_episodes(
    season_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    language: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    query = select(Episode).where(Episode.season_id == season_id)
    count_query = select(func.count(Episode.id)).where(Episode.season_id == season_id)

    if status_filter:
        query = query.where(Episode.status == status_filter)
        count_query = count_query.where(Episode.status == status_filter)
    if search:
        q = f"%{search}%"
        query = query.where(or_(Episode.title.ilike(q), Episode.content_group.ilike(q)))
        count_query = count_query.where(or_(Episode.title.ilike(q), Episode.content_group.ilike(q)))
    if language:
        query = query.where(Episode.language == language)
        count_query = count_query.where(Episode.language == language)

    total = (await db.execute(count_query)).scalar() or 0
    total_pages = max(1, ceil(total / page_size))

    query = query.order_by(Episode.episode_number).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    episodes = result.scalars().all()

    return {
        "items": [EpisodeResponse.model_validate(e).model_dump(mode="json") for e in episodes],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.post("/seasons/{season_id}/episodes", response_model=EpisodeResponse, status_code=201)
async def create_episode(
    season_id: str,
    data: EpisodeCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    season_result = await db.execute(select(Season).where(Season.id == season_id))
    if not season_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Season not found")

    existing = await db.execute(
        select(Episode).where(
            Episode.content_group == data.content_group,
            Episode.language == data.language,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"An episode with content_group '{data.content_group}' and language '{data.language}' already exists."
        )

    episode = Episode(
        season_id=season_id,
        episode_number=data.episode_number,
        title=data.title,
        duration_seconds=data.duration_seconds,
        language=data.language,
        content_group=data.content_group,
        synopsis=data.synopsis,
        status=PublishStatus(data.status),
    )
    db.add(episode)
    await db.flush()
    await db.refresh(episode)
    return EpisodeResponse.model_validate(episode)


@router.get("/episodes/{episode_id}", response_model=EpisodeResponse)
async def get_episode(
    episode_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return EpisodeResponse.model_validate(episode)


@router.put("/episodes/{episode_id}", response_model=EpisodeResponse)
async def update_episode(
    episode_id: str,
    data: EpisodeUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    update_data = data.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = PublishStatus(update_data["status"])

    if "content_group" in update_data or "language" in update_data:
        cg = update_data.get("content_group", episode.content_group)
        lang = update_data.get("language", episode.language)
        existing = await db.execute(
            select(Episode).where(
                Episode.content_group == cg,
                Episode.language == lang,
                Episode.id != episode.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"An episode with content_group '{cg}' and language '{lang}' already exists."
            )

    for key, value in update_data.items():
        setattr(episode, key, value)

    await db.flush()
    await db.refresh(episode)
    return EpisodeResponse.model_validate(episode)


@router.delete("/episodes/{episode_id}", status_code=204)
async def delete_episode(
    episode_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    await db.delete(episode)
    await db.flush()


# ---- Artwork Upload ----
@router.post("/artwork/{entity_type}/{entity_id}", response_model=ArtworkResponse, status_code=201)
async def upload_artwork(
    entity_type: str,
    entity_id: str,
    artwork_type: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    if artwork_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid artwork type '{artwork_type}'. Must be one of: {', '.join(ALLOWED_TYPES)}"
        )

    if entity_type == "show":
        slot_condition = Artwork.show_id == entity_id
    elif entity_type == "episode":
        slot_condition = Artwork.episode_id == entity_id
    else:
        raise HTTPException(status_code=400, detail="entity_type must be 'show' or 'episode'")

    # Fail fast on an unknown entity so bad uploads return a clean 404 rather than
    # a foreign-key error at flush time.
    try:
        entity_uuid = uuid.UUID(entity_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity_type == "show":
        entity_row = await db.execute(select(Show.id).where(Show.id == entity_uuid))
    else:
        entity_row = await db.execute(select(Episode.id).where(Episode.id == entity_uuid))
    if entity_row.first() is None:
        raise HTTPException(status_code=404, detail=f"{entity_type.capitalize()} not found")

    file_data = await file.read()
    is_valid, errors, metadata = validate_artwork(file_data, artwork_type)

    if not is_valid:
        raise HTTPException(status_code=422, detail={"errors": errors})

    storage = get_storage()
    ext = os.path.splitext(file.filename or "upload.jpg")[1]
    file_path = f"artwork/{entity_type}/{entity_id}/{artwork_type}{ext}"

    # One canonical image per slot: drop any existing artwork of this type (e.g.
    # a placeholder generated at seed time) before writing, so a real upload takes
    # effect and the entity's artwork list stays clean.
    old_artworks = (
        await db.execute(
            select(Artwork).where(slot_condition, Artwork.artwork_type == artwork_type)
        )
    ).scalars().all()
    for old in old_artworks:
        await storage.delete_file(old.file_path)
        await db.delete(old)
    await db.flush()

    await storage.save_file(file_data, file_path, file.content_type or "image/jpeg")

    artwork = Artwork(
        artwork_type=artwork_type,
        file_path=file_path,
        width=metadata["width"],
        height=metadata["height"],
        file_size_bytes=metadata["file_size_bytes"],
    )
    if entity_type == "show":
        artwork.show_id = entity_id
    else:
        artwork.episode_id = entity_id

    db.add(artwork)
    await db.flush()
    await db.refresh(artwork)
    return ArtworkResponse.model_validate(artwork)


@router.get("/artwork/{entity_type}/{entity_id}", response_model=list)
async def list_artworks(
    entity_type: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    if entity_type == "show":
        result = await db.execute(select(Artwork).where(Artwork.show_id == entity_id))
    elif entity_type == "episode":
        result = await db.execute(select(Artwork).where(Artwork.episode_id == entity_id))
    else:
        raise HTTPException(status_code=400, detail="entity_type must be 'show' or 'episode'")

    artworks = result.scalars().all()
    return [ArtworkResponse.model_validate(a).model_dump(mode="json") for a in artworks]


# ---- Video upload (external media) ----
MAX_VIDEO_BYTES = 250 * 1024 * 1024  # 250 MB


async def _resolve_episode(db: AsyncSession, episode_id: str) -> Episode:
    try:
        episode_uuid = uuid.UUID(episode_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Episode not found")
    result = await db.execute(select(Episode).where(Episode.id == episode_uuid))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


def _video_meta(episode: Episode, path: Path | None) -> dict:
    return {
        "episode_id": str(episode.id),
        "content_group": episode.content_group,
        "uploaded": path is not None,
        "file_path": f"videos/{path.name}" if path else None,
        "ext": path.suffix.lower() if path else None,
        "file_size_bytes": path.stat().st_size if path else None,
    }


@router.get("/videos/{episode_id}", response_model=dict)
async def get_episode_video(
    episode_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    """Report whether an episode has a playable video file (uploaded or generated)."""
    episode = await _resolve_episode(db, episode_id)
    return _video_meta(episode, find_video_file(episode.content_group))


@router.post("/videos/{episode_id}", response_model=dict, status_code=201)
async def upload_episode_video(
    episode_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    """Upload a real video (MP4/WebM) for an episode.

    Videos live per content_group, so all language variants of an episode share
    one file, and the upload replaces whatever was there before (including the
    generated placeholder clip). The file is probed with ffprobe when available
    so a corrupt/non-video upload is rejected rather than served.
    """
    episode = await _resolve_episode(db, episode_id)

    ext = Path(file.filename or "video.mp4").suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail={"errors": [
                f"Unsupported file type '{ext or '(none)'}'. "
                f"Upload an MP4 or WebM video."
            ]},
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail={"errors": ["The uploaded file is empty."]})
    if len(data) > MAX_VIDEO_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"errors": [f"Video exceeds the {MAX_VIDEO_BYTES // (1024 * 1024)} MB upload limit."]},
        )

    videos_dir = Path(settings.STORAGE_LOCAL_PATH) / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    # Probe a temp file first so a rejected upload never destroys the video that
    # was already there; only on success do we swap it in as the canonical file.
    tmp = videos_dir / f"{episode.content_group}.uploading{ext}"
    with open(tmp, "wb") as f:
        f.write(data)

    if not await probe_video_file(tmp):
        tmp.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail={"errors": [
                "The file was not recognized as a playable video. "
                "Upload a valid MP4 or WebM file (H.264/VP8/VP9 + AAC/Opus)."
            ]},
        )

    # One canonical file per content group: drop any previous variant (a generated
    # placeholder .mp4 or an older real upload), then move the validated file in.
    delete_video_file(episode.content_group)
    target = videos_dir / f"{episode.content_group}{ext}"
    os.replace(tmp, target)
    return _video_meta(episode, target)


@router.delete("/videos/{episode_id}", status_code=204)
async def delete_episode_video(
    episode_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Remove an episode's video file (admin only)."""
    episode = await _resolve_episode(db, episode_id)
    delete_video_file(episode.content_group)


# ---- Validation ----
@router.get("/validation-report", response_model=ValidationReport)
async def validation_report(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    report = await get_validation_issues(db)
    return ValidationReport(**report)


# ---- Publish ----
@router.post("/catalog/publish", response_model=PublishRunResponse)
async def trigger_publish(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    run = await publish_catalogue(db, user.get("sub", "unknown"))
    if run.outcome == "failed":
        raise HTTPException(status_code=422, detail={
            "message": "Publish failed due to validation errors",
            "run_id": str(run.id),
            "error": run.error_message,
        })
    return PublishRunResponse.model_validate(run)


@router.get("/publish-runs", response_model=list)
async def list_publish_runs(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("editor", "admin")),
):
    result = await db.execute(
        select(PublishRun).order_by(PublishRun.started_at.desc()).limit(limit)
    )
    runs = result.scalars().all()
    return [PublishRunResponse.model_validate(r).model_dump(mode="json") for r in runs]
