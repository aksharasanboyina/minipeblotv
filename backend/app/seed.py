import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session, init_db
from app.models import Episode, PublishStatus, Season, Show
from app.services.placeholder_art import provision_missing_artwork
from app.services.placeholder_video import provision_videos
from app.services.publish import get_validation_issues, publish_catalogue
from app.services.storage import get_storage

# seed.py lives inside the app package; the dataset sits at the backend repo root.
SEED_FILE = Path(__file__).resolve().parent.parent / "seed_shows.json"


def persist_data_issues(skipped_issues: list, notes: list = None):
    """Write seed-time data-quality issues so the validation report can surface them.

    - seed_skipped: rows rejected at import (duplicate language variants, etc.)
    - seed_notes: imported rows flagged as deliberately imperfect in the source
      data (e.g. ep_0036 declaring artwork_available: []).
    """
    data_issues = {
        "seed_skipped": skipped_issues,
        "seed_notes": notes or [],
    }
    issues_path = Path(settings.STORAGE_LOCAL_PATH) / "data_issues.json"
    issues_path.parent.mkdir(parents=True, exist_ok=True)
    with open(issues_path, "w", encoding="utf-8") as f:
        json.dump(data_issues, f, indent=2, ensure_ascii=False)


def read_existing_issues() -> dict:
    issues_path = Path(settings.STORAGE_LOCAL_PATH) / "data_issues.json"
    if issues_path.exists():
        try:
            with open(issues_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def collect_seed_notes() -> list:
    """Notes for imported rows that are deliberately imperfect in the source data.

    ep_0036 declares artwork_available: [] (published with no artwork supplied).
    It *is* imported and gets a generated placeholder thumbnail so the catalogue
    can ship; the note keeps the imperfection visible for a human to fix later.
    """
    if not SEED_FILE.exists():
        return []
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        rows = json.load(f)

    notes = []
    for ep_data in rows:
        if ep_data.get("status") != "published":
            continue
        if ep_data.get("artwork_available"):
            continue
        notes.append({
            "entity_type": "episode",
            "episode_id": ep_data["episode_id"],
            "entity_name": f"{ep_data.get('show_title')} {ep_data.get('episode_title')} ({ep_data.get('language', 'en')})",
            "reason": (
                f"Seed row {ep_data['episode_id']} declares artwork_available: [] - no "
                "artwork was supplied for this published episode. A generated placeholder "
                "thumbnail is attached so the catalogue can ship, but upload real artwork "
                "through the CMS before launch to clear this note."
            ),
        })
    return notes


async def import_episode_rows(db, episodes_data: list) -> dict:
    """Insert seed rows, deduplicating deliberately-imperfect data.

    Returns:
        episodes_imported: number of rows inserted
        shows_imported: number of distinct shows created
        skipped_issues: per-row data-quality notes for rows that were not imported
    """
    shows_cache = {}
    seasons_cache = {}
    seen_variants = set()
    skipped_issues = []
    imported = 0

    # Track (content_group, language) to dedupe deliberately-imperfect seed rows:
    # the (content_group, language) uniqueness rule is enforced at the DB level,
    # so duplicate variant rows can never be imported - keep the first, record the rest.
    for ep_data in episodes_data:
        cg = ep_data["content_group"]
        lang = ep_data.get("language", "en")
        variant_key = (cg, lang)

        if variant_key in seen_variants:
            skipped_issues.append({
                "entity_type": "episode",
                "episode_id": ep_data["episode_id"],
                "entity_name": f"{ep_data.get('show_title')} {ep_data.get('episode_title')} ({lang})",
                "reason": (
                    f"Duplicate language variant: content_group '{cg}' already has a "
                    f"{lang} language episode. The (content_group, language) uniqueness rule "
                    f"allows only one row per variant. This row (episode_id "
                    f"{ep_data['episode_id']}) was NOT imported - remove or fix it in the "
                    f"source file (backend/seed_shows.json) and re-seed to clear this note."
                ),
            })
            print(f"  SKIPPED duplicate variant: {ep_data['episode_id']} ({cg}, {lang})")
            continue

        seen_variants.add(variant_key)

        show_title = ep_data["show_title"]
        slug = ep_data["slug"]

        if slug not in shows_cache:
            show = Show(
                title=show_title,
                slug=slug,
                section=ep_data.get("section"),
                categories=ep_data.get("categories", []),
                synopsis=ep_data.get("synopsis", ""),
                status=PublishStatus(ep_data.get("status", "draft")),
            )
            db.add(show)
            await db.flush()
            shows_cache[slug] = show
        else:
            show = shows_cache[slug]

        season_key = (slug, ep_data["season_number"])
        if season_key not in seasons_cache:
            season = Season(
                show_id=show.id,
                season_number=ep_data["season_number"],
            )
            db.add(season)
            await db.flush()
            seasons_cache[season_key] = season
        else:
            season = seasons_cache[season_key]

        episode = Episode(
            season_id=season.id,
            episode_number=ep_data["episode_number"],
            title=ep_data["episode_title"],
            duration_seconds=ep_data.get("duration_seconds"),
            language=lang,
            content_group=cg,
            synopsis=ep_data.get("synopsis", ""),
            status=PublishStatus(ep_data.get("status", "draft")),
        )
        db.add(episode)
        imported += 1

    await db.commit()
    return {
        "episodes_imported": imported,
        "shows_imported": len(shows_cache),
        "skipped_issues": skipped_issues,
    }


async def seed():
    await init_db()

    if not SEED_FILE.exists():
        print(f"Seed file not found at {SEED_FILE}")
        return

    with open(SEED_FILE, "r", encoding="utf-8") as f:
        episodes_data = json.load(f)

    async with async_session() as db:
        existing = (await db.execute(select(Show))).scalars().first()

        skipped = []
        if existing:
            print("Database already seeded; ensuring placeholder artwork.")
            skipped = read_existing_issues().get("seed_skipped", [])
        else:
            summary = await import_episode_rows(db, episodes_data)
            skipped = summary["skipped_issues"]
            print(
                f"Seeded {summary['episodes_imported']} episode rows across "
                f"{summary['shows_imported']} shows."
            )
            if skipped:
                print(
                    f"Skipped {len(skipped)} duplicate-language-variant row(s) "
                    "(recorded in data_issues.json and surfaced in the validation report)."
                )

        art = await provision_missing_artwork(db)
        if art["shows"] or art["episodes"]:
            print(
                f"Provisioned placeholder artwork for {art['shows']} published show slot(s) "
                f"and {art['episodes']} published episode(s)."
            )

        await provision_videos(db)

        persist_data_issues(skipped, notes=collect_seed_notes())

        # First-boot auto-publish: once the seeded catalogue is valid (artwork
        # provisioned above) and no live catalogue exists yet, publish so the
        # viewer has content out of the box. Later publishes are admin-driven.
        storage = get_storage()
        if await storage.read_json("catalogues/catalogue.json") is None:
            validation = await get_validation_issues(db)
            if validation["can_publish"]:
                run = await publish_catalogue(db, "seed-boot")
                # publish_catalogue flushes but does not commit; the caller (get_db
                # for API routes) commits, so the boot path must too or the run row
                # would be rolled back when this session closes.
                await db.commit()
                print(
                    f"Auto-published initial catalogue: {run.outcome}, "
                    f"{run.shows_published} shows / {run.episodes_published} episodes."
                )
            else:
                print(
                    f"Skipping auto-publish: validation has "
                    f"{len(validation['blocking'])} blocking issue(s)."
                )
        else:
            print("Catalogue already published; leaving live catalogue as-is.")


if __name__ == "__main__":
    asyncio.run(seed())
