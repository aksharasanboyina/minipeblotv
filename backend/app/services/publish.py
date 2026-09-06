from datetime import datetime, timezone
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import Episode, PublishRun, PublishRunOutcome, PublishStatus, Season, Show
from app.services.placeholder_video import find_video_file
from app.services.storage import get_storage


async def get_validation_issues(db: AsyncSession) -> dict:
    blocking = []
    warnings = []

    result = await db.execute(
        select(Show).options(
            selectinload(Show.seasons).selectinload(Season.episodes).selectinload(Episode.artworks),
            selectinload(Show.artworks),
        )
    )
    shows = result.scalars().all()

    for show in shows:
        show_issues = []

        if show.status == PublishStatus.published and not show.section:
            show_issues.append(
                f"Published show '{show.title}' has no section assigned. "
                "Go to the show editor and assign a section before publishing."
            )

        if show.status == PublishStatus.published:
            poster = [a for a in show.artworks if a.artwork_type == "poster"]
            banner = [a for a in show.artworks if a.artwork_type == "banner"]
            if not poster:
                show_issues.append(
                    f"Show '{show.title}' is published but has no poster artwork. "
                    "Upload a poster (600x900, JPEG/PNG, max 200KB)."
                )
            if not banner:
                show_issues.append(
                    f"Show '{show.title}' is published but has no banner artwork. "
                    "Upload a banner (1280x720, JPEG/PNG, max 200KB)."
                )

        for season in show.seasons:
            for ep in season.episodes:
                if ep.status != PublishStatus.published:
                    continue

                ep_issues = []

                if not ep.duration_seconds or ep.duration_seconds <= 0:
                    ep_issues.append(
                        f"Episode '{ep.title}' (S{season.season_number}E{ep.episode_number}, {ep.language}) "
                        "has no duration. Set a duration in seconds before publishing."
                    )

                thumb = [a for a in ep.artworks if a.artwork_type == "thumbnail"]
                if not thumb:
                    ep_issues.append(
                        f"Episode '{ep.title}' (S{season.season_number}E{ep.episode_number}, {ep.language}) "
                        "has no thumbnail. Upload a thumbnail (640x360, JPEG/PNG, max 200KB)."
                    )

                if ep_issues:
                    if season.season_number == 0:
                        warnings.extend([{"entity_type": "episode", "entity_id": str(ep.id),
                                         "entity_name": f"{show.title} S0E{ep.episode_number} ({ep.language})",
                                         "issues": ep_issues}])
                    else:
                        blocking.extend([{"entity_type": "episode", "entity_id": str(ep.id),
                                         "entity_name": f"{show.title} S{season.season_number}E{ep.episode_number} ({ep.language})",
                                         "issues": ep_issues}])

        if show_issues:
            blocking.append({
                "entity_type": "show",
                "entity_id": str(show.id),
                "entity_name": show.title,
                "issues": show_issues,
            })

    # Surface seed-level data-quality notes (duplicate language variants, rows
    # declared artwork-less in the source, etc.) that were recorded at import time.
    # These are surfaced as WARNINGS with fix guidance rather than as blocking
    # issues, which could never be cleared through the CMS/API.
    import json as _json
    from pathlib import Path as _Path

    from app.core.config import settings as _settings
    issues_file = _Path(_settings.STORAGE_LOCAL_PATH) / "data_issues.json"
    if issues_file.exists():
        try:
            with open(issues_file, "r", encoding="utf-8") as f:
                data_issues = _json.load(f)
            entries = list(data_issues.get("seed_skipped", [])) + list(
                data_issues.get("seed_notes", [])
            )
            for skipped in entries:
                warnings.append({
                    "entity_type": skipped.get("entity_type", "episode"),
                    "entity_id": skipped.get("episode_id", ""),
                    "entity_name": skipped.get("entity_name", "unknown"),
                    "issues": [skipped.get("reason", "Data quality issue")],
                })
        except Exception:
            pass

    return {
        "blocking": blocking,
        "warnings": warnings,
        "can_publish": len(blocking) == 0,
    }


async def build_catalogue(db: AsyncSession) -> dict:
    result = await db.execute(
        select(Show).options(
            selectinload(Show.seasons).selectinload(Season.episodes).selectinload(Episode.artworks),
            selectinload(Show.artworks),
        ).where(Show.status == PublishStatus.published)
        .order_by(Show.title)
    )
    shows = result.scalars().unique().all()

    section_map: Dict[str, list] = {}

    for show in shows:
        section = show.section or "uncategorized"

        poster = next((a for a in show.artworks if a.artwork_type == "poster"), None)
        banner = next((a for a in show.artworks if a.artwork_type == "banner"), None)

        catalogue_show = {
            "show_id": str(show.id),
            "title": show.title,
            "slug": show.slug,
            "section": section,
            "categories": show.categories or [],
            "synopsis": show.synopsis or "",
            "poster_url": f"/storage/{poster.file_path}" if poster else None,
            "banner_url": f"/storage/{banner.file_path}" if banner else None,
            "seasons": [],
            "has_trailer": False,
            "trailer_url": None,
        }

        trailer_entry = None

        sorted_seasons = sorted(show.seasons, key=lambda s: s.season_number)

        for season in sorted_seasons:
            if season.season_number == 0:
                for ep in season.episodes:
                    if ep.status == PublishStatus.published:
                        thumb = next((a for a in ep.artworks if a.artwork_type == "thumbnail"), None)
                        trailer_entry = {
                            "episode_id": str(ep.id),
                            "title": ep.title,
                            "languages": [ep.language],
                            "thumbnail_url": f"/storage/{thumb.file_path}" if thumb else None,
                        }
                        catalogue_show["has_trailer"] = True
                        catalogue_show["trailer_url"] = trailer_entry["thumbnail_url"]
                continue

            season_episodes = sorted(
                [ep for ep in season.episodes if ep.status == PublishStatus.published],
                key=lambda e: e.episode_number
            )

            cg_season: Dict[str, dict] = {}
            for ep in season_episodes:
                cg_key = ep.content_group
                thumb = next((a for a in ep.artworks if a.artwork_type == "thumbnail"), None)

                # The catalogue only advertises a playable episode when its video
                # file (uploaded or generated placeholder) actually exists on disk.
                has_video = (
                    settings.STORAGE_BACKEND != "r2" and find_video_file(cg_key) is not None
                )

                if cg_key not in cg_season:
                    cg_season[cg_key] = {
                        "episode_id": str(ep.id),
                        "title": ep.title,
                        "episode_number": ep.episode_number,
                        "duration_seconds": ep.duration_seconds,
                        "synopsis": ep.synopsis or "",
                        "languages": [ep.language],
                        "thumbnail_url": f"/storage/{thumb.file_path}" if thumb else None,
                        "video_url": f"/catalog/video/{ep.id}" if has_video else None,
                        "has_video": has_video,
                    }
                else:
                    if ep.language not in cg_season[cg_key]["languages"]:
                        cg_season[cg_key]["languages"].append(ep.language)

            season_entry = {
                "season_number": season.season_number,
                "episodes": list(cg_season.values()),
            }
            catalogue_show["seasons"].append(season_entry)

        if section not in section_map:
            section_map[section] = []
        section_map[section].append(catalogue_show)

    section_order = ["featured", "series", "minisodes", "songs"]
    sections = []
    for s in section_order:
        if s in section_map:
            sections.append({"section": s, "shows": section_map[s]})

    for s, shows_list in section_map.items():
        if s not in section_order:
            sections.append({"section": s, "shows": shows_list})

    catalogue = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
    }

    return catalogue


async def publish_catalogue(db: AsyncSession, user_id: str) -> PublishRun:
    run = PublishRun(
        published_by=user_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    storage = get_storage()

    try:
        validation = await get_validation_issues(db)
        if not validation["can_publish"]:
            run.completed_at = datetime.now(timezone.utc)
            run.outcome = PublishRunOutcome.failed
            run.error_message = f"Validation failed: {len(validation['blocking'])} blocking issues"
            await db.flush()
            return run

        catalogue = await build_catalogue(db)

        # Write a versioned copy (kept for rollback / auditing) first.
        versioned_path = f"catalogues/catalogue-{run.id}.json"
        await storage.save_json(catalogue, versioned_path)

        # Then atomically swap the live file a reader sees.
        # LocalStorage.save_json writes to a temp file and os.replace()s it into
        # place, so a reader never observes a half-written catalogue.
        live_path = "catalogues/catalogue.json"
        await storage.save_json(catalogue, live_path)

        current_result = await db.execute(
            select(PublishRun).where(PublishRun.is_current)
        )
        for old_run in current_result.scalars().all():
            old_run.is_current = False

        run.completed_at = datetime.now(timezone.utc)
        run.outcome = PublishRunOutcome.success
        run.catalogue_path = live_path
        run.is_current = True

        total_episodes = 0
        for section in catalogue.get("sections", []):
            run.shows_published += len(section.get("shows", []))
            for show in section.get("shows", []):
                for season in show.get("seasons", []):
                    total_episodes += len(season.get("episodes", []))
        run.episodes_published = total_episodes

        await db.flush()

        return run

    except Exception as e:
        run.completed_at = datetime.now(timezone.utc)
        run.outcome = PublishRunOutcome.failed
        run.error_message = str(e)
        await db.flush()
        return run
