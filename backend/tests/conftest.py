import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Test storage must live OUTSIDE the project tree: the repo sits under OneDrive on
# this machine, and OneDrive's sync service holds short-lived locks on newly
# written files (catalogue.json etc.), which made cleanup flaky. Env vars are set
# before importing the app so Settings picks them up (env overrides the .env file).
_TEST_STORAGE = Path(tempfile.gettempdir()) / "peblo-test-storage"
os.environ["STORAGE_LOCAL_PATH"] = str(_TEST_STORAGE)
# Video clip generation needs ffmpeg + encodes a file per content group - neither
# needed for the API tests, so disable it here (catalogue episodes then simply
# advertise has_video=false and the stream endpoint 404s, which tests assert on).
os.environ["FFMPEG_BIN"] = ""
# The app under test must not auto-seed/auto-publish (tests own the database).
os.environ["SEED_ON_START"] = "false"

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

# Make `app` importable when running pytest from the repo root or the backend dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

import app.core.database as database  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models import (  # noqa: E402
    Artwork,
    Episode,
    PublishRun,
    Season,
    Show,
)
from app.seed import (  # noqa: E402
    SEED_FILE,
    collect_seed_notes,
    import_episode_rows,
    persist_data_issues,
)
from app.services.placeholder_art import provision_missing_artwork  # noqa: E402

# Point the app's DB plumbing at a fresh engine with a NullPool so connections are
# never shared across pytest-asyncio's per-test event loops.
TEST_ENGINE = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
database.engine = TEST_ENGINE
database.async_session = async_sessionmaker(
    TEST_ENGINE, class_=AsyncSession, expire_on_commit=False
)

STORAGE_DIR = Path(settings.STORAGE_LOCAL_PATH)


def rmtree_retry(path: Path, attempts: int = 6):
    """Windows/OneDrive occasionally holds short-lived locks on storage files; retry."""
    for i in range(attempts):
        try:
            if path.exists():
                shutil.rmtree(path)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(1)


async def reset_database():
    """Create tables if needed and wipe all rows (tests own the database)."""
    await database.init_db()
    async with TEST_ENGINE.begin() as conn:
        for table in (
            PublishRun.__table__,
            Artwork.__table__,
            Episode.__table__,
            Season.__table__,
            Show.__table__,
        ):
            await conn.execute(table.delete())

    # Storage artifacts left behind by earlier runs (validation reads data_issues.json,
    # publish writes catalogue.json, placeholder artwork/videos live under storage/).
    issues_file = STORAGE_DIR / "data_issues.json"
    for _ in range(6):
        try:
            if issues_file.exists():
                issues_file.unlink()
            break
        except PermissionError:
            time.sleep(1)
    for name in ("catalogues", "artwork", "videos"):
        rmtree_retry(STORAGE_DIR / name)


async def seed_episodes():
    """Import the real seed dataset with the same semantics as the app's first boot."""
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        rows = json.load(f)
    async with database.async_session() as db:
        summary = await import_episode_rows(db, rows)
    persist_data_issues(summary["skipped_issues"], notes=collect_seed_notes())


async def provision_artwork():
    """Provision generated placeholder artwork (same helper the app boot runs).

    The demo is meant to run out of the box, so every published entity gets a
    spec-conforming placeholder: shows get poster + banner, episodes (including
    the deliberately art-less ep_0036) get a thumbnail. Uploading real artwork
    through the CMS replaces the placeholder.
    """
    async with database.async_session() as db:
        await provision_missing_artwork(db)


@pytest.fixture(autouse=True)
async def seeded_db():
    """Every test starts from a fresh, seeded database with artwork provisioned."""
    await reset_database()
    await seed_episodes()
    await provision_artwork()
    yield
