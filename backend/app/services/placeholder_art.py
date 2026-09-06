"""Placeholder artwork for a fresh seed.

The challenge's artwork assets folder ships empty and no real image files exist
on a first boot, so without provisioning the validator would block *every*
published show and episode and the catalogue could never be published. These
generated placeholders satisfy the exact same server-side specs the upload
endpoint enforces (dimensions, aspect ratio, <200 KB - see reference.json /
app/services/artwork.py), so the product runs out of the box. Editors replace
them with real artwork through the CMS (uploading simply overwrites the same
slot), which is the production path.
"""

import colorsys
import hashlib
import io

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Artwork, Episode, PublishStatus, Season, Show
from app.services.artwork import ARTWORK_SPECS
from app.services.storage import get_storage

# Show-level slots that the validator demands for a published show.
SHOW_ARTWORK_TYPES = ("poster", "banner")
# Episode-level slot the validator demands for every published episode (and the
# only episode artwork the viewer catalogue references).
EPISODE_ARTWORK_TYPE = "thumbnail"


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Best-effort TTF font, falling back to Pillow's bundled font."""
    try:
        from PIL import ImageFont as _f

        return _f.load_default(size=size)
    except TypeError:  # Pillow < 10.1: load_default() takes no size
        return ImageFont.load_default()


def _color_for(*parts: str) -> tuple:
    """Derive a stable, mid-saturation RGB color from an identifier."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    hue = int(digest[:4], 16) / 65535.0
    # HSL -> RGB with fixed s/l so the text overlay stays readable.
    r, g, b = colorsys.hls_to_rgb(hue, 0.55, 0.55)
    return int(r * 255), int(g * 255), int(b * 255)


def generate_placeholder_bytes(artwork_type: str, label: str = "Peblo TV") -> bytes:
    """Return a JPEG meeting the artwork spec for the given type, as bytes."""
    spec = ARTWORK_SPECS[artwork_type]
    width, height = spec["target_width"], spec["target_height"]
    color = _color_for(artwork_type, label)

    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)

    # Vertical lightening so cards are easy to tell apart and text stays readable.
    for i in range(height):
        shade = int(90 * (i / height))
        draw.line([(0, i), (width, i)], fill=tuple(min(255, c + shade) for c in color))

    border = max(6, width // 60)
    draw.rectangle([border, border, width - border, height - border], outline=(255, 255, 255), width=border)

    font_title = _load_font(max(18, height // 22))
    font_small = _load_font(max(12, height // 40))

    def center_text(text, y, font, fill=(255, 255, 255)):
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((width - (box[2] - box[0])) / 2, y), text, font=font, fill=fill)

    center_text("Peblo TV", int(height * 0.30), font_title)
    center_text(label[:60], int(height * 0.52), font_small, fill=(240, 240, 240))
    center_text(f"{artwork_type} placeholder  ·  {width}x{height}", int(height * 0.66), font_small, fill=(220, 220, 220))

    # Encode as JPEG, tightening quality until comfortably under the 200 KB cap.
    quality = 85
    while quality > 30:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) < spec["max_bytes"] * 0.95:
            break
        quality -= 10
    return data


async def provision_missing_artwork(db: AsyncSession) -> dict:
    """Attach generated placeholder artwork to published entities missing it.

    Idempotent: entities that already have the required artwork type are left
    untouched (their art may be a real CMS upload). Runs on every boot so a
    database that was seeded before this feature also gets artwork.
    """
    storage = get_storage()

    result = await db.execute(
        select(Show).options(
            selectinload(Show.seasons).selectinload(Season.episodes).selectinload(Episode.artworks),
            selectinload(Show.artworks),
        )
    )
    shows = result.scalars().unique().all()

    created_shows = 0
    created_episodes = 0

    for show in shows:
        if show.status != PublishStatus.published:
            continue

        for artwork_type in SHOW_ARTWORK_TYPES:
            if any(a.artwork_type == artwork_type for a in show.artworks):
                continue
            data = generate_placeholder_bytes(artwork_type, label=show.title)
            file_path = f"artwork/seed/{show.slug}/{artwork_type}.jpg"
            await storage.save_file(data, file_path, "image/jpeg")
            db.add(
                Artwork(
                    show_id=show.id,
                    artwork_type=artwork_type,
                    file_path=file_path,
                    width=ARTWORK_SPECS[artwork_type]["target_width"],
                    height=ARTWORK_SPECS[artwork_type]["target_height"],
                    file_size_bytes=len(data),
                )
            )
            created_shows += 1

        for season in show.seasons:
            for ep in season.episodes:
                if ep.status != PublishStatus.published:
                    continue
                if any(a.artwork_type == EPISODE_ARTWORK_TYPE for a in ep.artworks):
                    continue
                data = generate_placeholder_bytes(
                    EPISODE_ARTWORK_TYPE,
                    label=f"{show.title} · {ep.title}",
                )
                file_path = f"artwork/seed/{show.slug}/{ep.content_group}-{ep.language}.jpg"
                await storage.save_file(data, file_path, "image/jpeg")
                db.add(
                    Artwork(
                        episode_id=ep.id,
                        artwork_type=EPISODE_ARTWORK_TYPE,
                        file_path=file_path,
                        width=ARTWORK_SPECS[EPISODE_ARTWORK_TYPE]["target_width"],
                        height=ARTWORK_SPECS[EPISODE_ARTWORK_TYPE]["target_height"],
                        file_size_bytes=len(data),
                    )
                )
                created_episodes += 1

    await db.commit()
    return {"shows": created_shows, "episodes": created_episodes}
