"""Playable placeholder clips for a fresh seed.

No real video files ship with the project, so the viewer has nothing to play. On
boot (when ffmpeg is available) this generates a short, distinct MP4 per published
content group - a real H.264 file the HTML5 player can stream. Generation is
idempotent (existing files are kept) and skips cleanly when ffmpeg is missing
(settings.FFMPEG_BIN empty or not on PATH), leaving catalogue episodes flagged
has_video=false instead of crashing the boot.

The clips are demo stand-ins only: in production, real media would be uploaded or
referenced per content group and served through the same stream endpoint.
"""

import asyncio
import hashlib
import os
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import PublishStatus, Season, Show

VIDEO_DIR_NAME = "videos"
CLIP_SECONDS = 8
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 360

# Extensions the player can stream (browser support for mp4/webm is universal).
ALLOWED_VIDEO_EXTENSIONS = (".mp4", ".webm")

MEDIA_TYPES = {".mp4": "video/mp4", ".webm": "video/webm"}


def _hue_for(content_group: str) -> int:
    digest = hashlib.sha256(content_group.encode("utf-8")).hexdigest()
    return int(digest[:4], 16) % 360


def _ffmpeg_path() -> str | None:
    if not settings.FFMPEG_BIN:
        return None
    found = shutil.which(settings.FFMPEG_BIN)
    if found:
        return found
    # Allow an explicit path that isn't on PATH (portable Windows builds etc.).
    return settings.FFMPEG_BIN if Path(settings.FFMPEG_BIN).exists() else None


def _probe_binary() -> str | None:
    """Locate ffprobe: next to an explicitly-configured ffmpeg, or on PATH.

    Note: shutil.which() returns an explicit path as-is when the file exists, so
    an absolute FFMPEG_BIN must be detected by its path shape, not by which().
    """
    ffmpeg = settings.FFMPEG_BIN
    if not ffmpeg:
        return None
    is_explicit = (
        os.sep in ffmpeg or "/" in ffmpeg or "\\" in ffmpeg or ffmpeg.lower().endswith(".exe")
    )
    if is_explicit:
        suffix = ".exe" if ffmpeg.lower().endswith(".exe") else ""
        probe = Path(ffmpeg).with_name("ffprobe" + suffix)
        return str(probe) if probe.exists() else None
    return shutil.which("ffprobe")


def video_file_path(content_group: str) -> Path:
    """Canonical generated-placeholder location for a content group."""
    return Path(settings.STORAGE_LOCAL_PATH) / VIDEO_DIR_NAME / f"{content_group}.mp4"


def find_video_file(content_group: str) -> Path | None:
    """Return the on-disk video for a content group (any allowed extension), if any.

    Real uploads may be .webm while generated placeholders are .mp4; exactly one
    file exists per content group at a time, and everything (generation guard,
    catalogue has_video, streaming) goes through this helper.
    """
    base = Path(settings.STORAGE_LOCAL_PATH) / VIDEO_DIR_NAME
    for ext in ALLOWED_VIDEO_EXTENSIONS:
        candidate = base / f"{content_group}{ext}"
        if candidate.exists():
            return candidate
    return None


def media_type_for(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.lower(), "video/mp4")


def delete_video_file(content_group: str) -> None:
    """Remove every file variant for a content group (keeps one canonical video)."""
    for ext in ALLOWED_VIDEO_EXTENSIONS:
        candidate = Path(settings.STORAGE_LOCAL_PATH) / VIDEO_DIR_NAME / f"{content_group}{ext}"
        if candidate.exists():
            candidate.unlink()


async def probe_video_file(path: Path) -> bool:
    """Confirm the file is actually playable video (ffprobe). True when no ffprobe."""
    probe = _probe_binary()
    if not probe:
        return True  # cannot verify - trust the upload (tests / ffmpeg-less hosts)
    proc = await asyncio.create_subprocess_exec(
        probe, "-v", "error", "-show_entries", "format=format_name",
        "-of", "default=nw=1:nk=1", str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return proc.returncode == 0 and bool(out.strip())


async def _generate_clip(ffmpeg: str, content_group: str) -> bool:
    out_path = video_file_path(content_group)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={VIDEO_WIDTH}x{VIDEO_HEIGHT}:rate=24",
        "-vf", f"hue=h={_hue_for(content_group)}:s=1",
        "-t", str(CLIP_SECONDS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-an",
        str(out_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return proc.returncode == 0 and out_path.exists()


async def provision_videos(db: AsyncSession) -> dict:
    """Generate a playable clip for every published content group missing one.

    Runs on every boot; only missing files are created. Skips trailers (season 0)
    - they are show-level flourishes, not normal watchable episodes.
    """
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        print("Skipping placeholder video generation (ffmpeg not available).")
        return {"videos_created": 0, "videos_total": 0}

    result = await db.execute(
        select(Show).options(
            selectinload(Show.seasons).selectinload(Season.episodes),
        )
    )
    content_groups = set()
    for show in result.scalars().unique().all():
        if show.status != PublishStatus.published:
            continue
        for season in show.seasons:
            if season.season_number == 0:
                continue
            for ep in season.episodes:
                if ep.status == PublishStatus.published:
                    content_groups.add(ep.content_group)

    missing = [cg for cg in content_groups if find_video_file(cg) is None]

    # Generate a handful in parallel; libx264 is single-threaded per file.
    semaphore = asyncio.Semaphore(4)

    async def guarded(cg: str) -> bool:
        async with semaphore:
            return await _generate_clip(ffmpeg, cg)

    results = await asyncio.gather(*(guarded(cg) for cg in missing)) if missing else []
    created = sum(1 for ok in results if ok)
    failed = len(missing) - created
    if created:
        print(f"Provisioned {created} placeholder video clip(s).")
    if failed:
        print(f"Warning: failed to generate {failed} video clip(s).")
    return {"videos_created": created, "videos_total": len(content_groups)}
