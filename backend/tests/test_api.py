import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.main import app
from app.models import Artwork
from app.services.placeholder_art import generate_placeholder_bytes

# Content group of the deliberately art-less seed episode (ep_0036): its source row
# declares artwork_available: [] but the boot flow provisions a placeholder so the
# catalogue can ship; it stays recorded as a data note.
SEED_NOTE_CONTENT_GROUP = "discover-india-with-moti-s01e04"

VIEWER_EMAIL = "kids@peblo.tv"
VIEWER_PASSWORD = "peblo123"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _token(payload):
    import httpx
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/token", json=payload)
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]


async def get_editor_token():
    return await _token({"user_id": "editor@peblo.tv", "role": "editor"})


async def get_admin_token():
    return await _token({"user_id": "admin@peblo.tv", "role": "admin"})


async def get_viewer_token():
    import httpx
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/auth/viewer/token",
            json={"email": VIEWER_EMAIL, "password": VIEWER_PASSWORD},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]


async def admin_headers():
    return {"Authorization": f"Bearer {await get_admin_token()}"}


async def editor_headers():
    return {"Authorization": f"Bearer {await get_editor_token()}"}


async def viewer_headers():
    return {"Authorization": f"Bearer {await get_viewer_token()}"}


async def set_episode_status(client, headers, episode_id, status):
    resp = await client.put(f"/admin/episodes/{episode_id}", json={"status": status}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def find_seed_episode_id(client, headers, content_group):
    """Locate a seeded episode by content group through the admin API."""
    shows = (await client.get(
        "/admin/shows", params={"page_size": 100}, headers=headers
    )).json()
    for show in shows["items"]:
        seasons = (await client.get(f"/admin/shows/{show['id']}/seasons", headers=headers)).json()
        for season in seasons:
            if season["season_number"] != 1:
                continue
            episodes = (await client.get(
                f"/admin/seasons/{season['id']}/episodes",
                params={"page_size": 100},
                headers=headers,
            )).json()
            for ep in episodes["items"]:
                if ep["content_group"] == content_group:
                    return ep["id"]
    raise AssertionError(f"episode with content_group {content_group} not found")


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_auth_required():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/admin/shows")
        assert resp.status_code in (403, 401)


@pytest.mark.asyncio
async def test_editor_can_list_shows(client):
    headers = await editor_headers()
    resp = await client.get("/admin/shows", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_editor_cannot_publish(client):
    headers = await editor_headers()
    resp = await client.post("/admin/catalog/publish", headers=headers)
    assert resp.status_code == 403


# ---- Viewer auth ----


@pytest.mark.asyncio
async def test_viewer_login():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Correct credentials -> viewer token.
        resp = await c.post(
            "/auth/viewer/token",
            json={"email": VIEWER_EMAIL, "password": VIEWER_PASSWORD},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "viewer"
        assert data["access_token"]

        # Wrong password -> 401.
        resp = await c.post(
            "/auth/viewer/token",
            json={"email": VIEWER_EMAIL, "password": "nope"},
        )
        assert resp.status_code == 401

        # Unknown account -> 401.
        resp = await c.post(
            "/auth/viewer/token",
            json={"email": "ghost@peblo.tv", "password": VIEWER_PASSWORD},
        )
        assert resp.status_code == 401

        # The CMS token issuer cannot mint viewer tokens...
        resp = await c.post("/auth/token", json={"user_id": "kids@peblo.tv", "role": "viewer"})
        assert resp.status_code == 422  # schema restricts roles to editor/admin

        # ...and cannot mint another user's role.
        resp = await c.post("/auth/token", json={"user_id": "admin@peblo.tv", "role": "editor"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_catalogue_requires_viewer(client):
    # No token at all -> 401 on every catalogue route.
    for path in ("/catalog", "/catalog/search?q=kite"):
        resp = await client.get(path)
        assert resp.status_code == 401, path

    # An admin (CMS role) token is not a viewer token -> 403.
    admin_headers_obj = await admin_headers()
    resp = await client.get("/catalog", headers=admin_headers_obj)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_catalogue_404_before_publish(client):
    # A valid viewer session sees the empty state (404) before the first publish.
    headers = await viewer_headers()
    resp = await client.get("/catalog", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_video_stream_requires_viewer(client):
    headers = await admin_headers()
    ep_id = await find_seed_episode_id(client, headers, SEED_NOTE_CONTENT_GROUP)

    # No token -> 401.
    resp = await client.get(f"/catalog/video/{ep_id}")
    assert resp.status_code == 401

    # Wrong role -> 403.
    resp = await client.get(f"/catalog/video/{ep_id}", headers=await admin_headers())
    assert resp.status_code == 403

    # Valid viewer token: the episode exists but no clip was generated in tests
    # (ffmpeg disabled), so the stream is a clean 404 - the endpoint is wired.
    resp = await client.get(f"/catalog/video/{ep_id}", headers=await viewer_headers())
    assert resp.status_code == 404

    # Viewer token via ?token= query (how <video> streams) is also accepted.
    viewer_token = await get_viewer_token()
    resp = await client.get(f"/catalog/video/{ep_id}?token={viewer_token}")
    assert resp.status_code == 404

    # Unknown episode -> 404.
    resp = await client.get(
        "/catalog/video/00000000-0000-0000-0000-000000000000",
        headers=await viewer_headers(),
    )
    assert resp.status_code == 404


# ---- Video upload ----


@pytest.mark.asyncio
async def test_upload_episode_video_and_stream(client):
    """External videos upload, replace, publish as watchable, and stream."""
    admin = await admin_headers()
    editor = await editor_headers()
    viewer = await viewer_headers()

    ep_id = await find_seed_episode_id(client, admin, SEED_NOTE_CONTENT_GROUP)

    # No video yet in tests (ffmpeg disabled at fixture level).
    state = (await client.get(f"/admin/videos/{ep_id}", headers=admin)).json()
    assert state["uploaded"] is False

    # An editor can upload an MP4 (editors may not publish, but may add media).
    fake_mp4 = b"not-a-real-mp4-but-probe-is-disabled-in-tests"
    upload = await client.post(
        f"/admin/videos/{ep_id}",
        files={"file": ("episode.mp4", fake_mp4, "video/mp4")},
        headers=editor,
    )
    assert upload.status_code == 201, upload.text
    meta = upload.json()
    assert meta["uploaded"] is True
    assert meta["ext"] == ".mp4"
    assert meta["content_group"] == SEED_NOTE_CONTENT_GROUP
    assert meta["file_size_bytes"] == len(fake_mp4)

    # State endpoint agrees.
    state = (await client.get(f"/admin/videos/{ep_id}", headers=admin)).json()
    assert state["uploaded"] is True
    assert state["ext"] == ".mp4"

    # Re-upload replaces the file rather than stacking duplicates.
    second = await client.post(
        f"/admin/videos/{ep_id}",
        files={"file": ("episode.webm", b"webm-bytes", "video/webm")},
        headers=admin,
    )
    assert second.status_code == 201, second.text
    assert second.json()["ext"] == ".webm"

    # Reject bad files cleanly.
    bad = await client.post(
        f"/admin/videos/{ep_id}",
        files={"file": ("episode.avi", b"x", "video/x-msvideo")},
        headers=admin,
    )
    assert bad.status_code == 422
    empty = await client.post(
        f"/admin/videos/{ep_id}",
        files={"file": ("episode.mp4", b"", "video/mp4")},
        headers=admin,
    )
    assert empty.status_code == 422
    missing = await client.post(
        "/admin/videos/00000000-0000-0000-0000-000000000000",
        files={"file": ("episode.mp4", b"x", "video/mp4")},
        headers=admin,
    )
    assert missing.status_code == 404

    # Publish: the episode is now advertised as watchable.
    await client.post("/admin/catalog/publish", headers=admin)
    catalogue = (await client.get("/catalog", headers=viewer)).json()
    watchable = [
        ep for s in catalogue["sections"] for sh in s["shows"]
        for season in sh["seasons"] for ep in season["episodes"]
        if ep["episode_id"] == ep_id
    ]
    assert len(watchable) == 1
    assert watchable[0]["has_video"] is True
    assert watchable[0]["video_url"] == f"/catalog/video/{ep_id}"

    # The stream serves the uploaded file (viewer-gated, header or ?token).
    stream = await client.get(f"/catalog/video/{ep_id}", headers=viewer)
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("video/webm")
    assert stream.content == b"webm-bytes"
    token = await get_viewer_token()
    stream = await client.get(f"/catalog/video/{ep_id}?token={token}")
    assert stream.status_code == 200

    # Admin can delete the video; it is no longer served.
    delete = await client.delete(f"/admin/videos/{ep_id}", headers=admin)
    assert delete.status_code == 204
    state = (await client.get(f"/admin/videos/{ep_id}", headers=admin)).json()
    assert state["uploaded"] is False
    gone = await client.get(f"/catalog/video/{ep_id}", headers=viewer)
    assert gone.status_code == 404

    # Editors cannot delete videos (admin-only), but GET state is allowed.
    delete_editor = await client.delete(f"/admin/videos/{ep_id}", headers=editor)
    assert delete_editor.status_code == 403


# ---- Boot / publish / validation ----


@pytest.mark.asyncio
async def test_boot_state_is_publishable_out_of_the_box(client):
    """A fresh boot provisions placeholder artwork, so the catalogue is publishable.

    The deliberate seed imperfections (the ep_9001 duplicate variant that never
    entered the DB, and ep_0036 whose source row declares no artwork) surface as
    WARNINGS with fix guidance - they must not brick publish.
    """
    headers = await admin_headers()
    report = (await client.get("/admin/validation-report", headers=headers)).json()

    assert report["blocking"] == []
    assert report["can_publish"] is True

    warning_text = "\n".join(
        f"{w['entity_name']}: {w['issues'][0]}" for w in report["warnings"]
    )
    # Duplicate hi variant surfaced as a warning, not a blocker.
    assert "The Lost Kite (v2)" in warning_text
    # ep_0036 recorded as a data note.
    assert "The Midnight Market" in warning_text
    assert "artwork_available: []" in warning_text

    # The catalogue is not live yet, so a logged-in viewer has nothing - until publish.
    resp = await client.get("/catalog", headers=await viewer_headers())
    assert resp.status_code == 404

    resp = await client.post("/admin/catalog/publish", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "success"
    assert data["shows_published"] == 7
    assert data["episodes_published"] == 64


@pytest.mark.asyncio
async def test_validation_blocks_missing_artwork_and_upload_resolves(client):
    """The validator keeps its teeth: drop an episode's thumbnail and publish is
    blocked; uploading a real spec-conforming thumbnail through the API clears it.
    """
    import app.core.database as database

    headers = await admin_headers()

    ep_id = await find_seed_episode_id(client, headers, SEED_NOTE_CONTENT_GROUP)

    # Strip the provisioned placeholder thumbnail from that episode.
    async with database.async_session() as db:
        await db.execute(
            delete(Artwork).where(
                Artwork.episode_id == ep_id, Artwork.artwork_type == "thumbnail"
            )
        )
        await db.commit()

    report = (await client.get("/admin/validation-report", headers=headers)).json()
    assert report["can_publish"] is False
    matching = [
        b for b in report["blocking"]
        if b["entity_id"] == ep_id and any("thumbnail" in i for i in b["issues"])
    ]
    assert matching, report["blocking"]

    resp = await client.post("/admin/catalog/publish", headers=headers)
    assert resp.status_code == 422

    # Fix it through the real upload pipeline with a spec-conforming image. The
    # upload must REPLACE the (deleted) placeholder slot - a single canonical row.
    thumb = generate_placeholder_bytes("thumbnail", label="test upload")
    upload = await client.post(
        f"/admin/artwork/episode/{ep_id}",
        files={"file": ("thumb.jpg", thumb, "image/jpeg")},
        params={"artwork_type": "thumbnail"},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text

    listing = (await client.get(f"/admin/artwork/episode/{ep_id}", headers=headers)).json()
    assert len(listing) == 1
    assert listing[0]["artwork_type"] == "thumbnail"

    report = (await client.get("/admin/validation-report", headers=headers)).json()
    assert report["blocking"] == []
    assert report["can_publish"] is True

    resp = await client.post("/admin/catalog/publish", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["outcome"] == "success"


@pytest.mark.asyncio
async def test_upload_rejects_bad_artwork(client):
    """The server-side artwork validation rejects files that miss the spec."""
    headers = await admin_headers()

    ep_id = await find_seed_episode_id(client, headers, SEED_NOTE_CONTENT_GROUP)

    # A 200x200 square is the wrong ratio for every slot and wrong dimensions.
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (200, 200), (120, 60, 200)).save(buf, format="JPEG")
    upload = await client.post(
        f"/admin/artwork/episode/{ep_id}",
        files={"file": ("square.jpg", buf.getvalue(), "image/jpeg")},
        params={"artwork_type": "thumbnail"},
        headers=headers,
    )
    assert upload.status_code == 422
    detail = upload.json()["detail"]
    assert detail["errors"], detail
    assert any("ratio" in e.lower() for e in detail["errors"])

    # Uploading to an unknown entity is a clean 404, not a server error.
    upload = await client.post(
        "/admin/artwork/episode/00000000-0000-0000-0000-000000000000",
        files={"file": ("square.jpg", buf.getvalue(), "image/jpeg")},
        params={"artwork_type": "thumbnail"},
        headers=headers,
    )
    assert upload.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_publish_full_catalogue(client):
    headers = await admin_headers()
    resp = await client.post("/admin/catalog/publish", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "success"
    assert data["shows_published"] == 7
    assert data["episodes_published"] == 64


# ---- Viewer catalogue ----


@pytest.mark.asyncio
async def test_catalog_available_after_publish(client):
    headers = await admin_headers()
    await client.post("/admin/catalog/publish", headers=headers)

    vheaders = await viewer_headers()
    resp = await client.get("/catalog", headers=vheaders)
    assert resp.status_code == 200
    data = resp.json()
    assert "sections" in data
    assert [s["section"] for s in data["sections"]] == ["featured", "series", "minisodes", "songs"]
    counts = [len(s["shows"]) for s in data["sections"]]
    assert counts == [1, 3, 1, 2], counts

    # Language variants of the same content group collapse into one episode entry.
    featured = data["sections"][0]["shows"]
    motis = next(s for s in featured if s["slug"] == "motis-many-lives")
    assert motis["has_trailer"] is True
    assert motis["trailer_url"] is not None
    assert all(season["season_number"] != 0 for season in motis["seasons"]), \
        "Season 0 must become a trailer, never a normal catalogue season"
    s1 = next(s for s in motis["seasons"] if s["season_number"] == 1)
    first_ep = s1["episodes"][0]
    assert set(first_ep["languages"]) == {"en", "hi"}
    # Video generation is disabled in tests, so episodes are catalogued as not
    # watchable yet (no clip file) - the field exists and is honest.
    assert first_ep["has_video"] is False
    assert first_ep["video_url"] is None

    # Every seeded episode is publishable now (ep_0036 included), so all of
    # Discover India's ten episodes appear - The Midnight Market among them.
    discover = next(s for s in data["sections"][2]["shows"] if s["slug"] == "discover-india-with-moti")
    discover_titles = [ep["title"] for season in discover["seasons"] for ep in season["episodes"]]
    assert "The Midnight Market" in discover_titles
    assert discover_titles == [
        "The Lost Kite", "Rain on the Roof", "A Bridge of Stones", "The Midnight Market",
        "Footprints in Flour", "The Whistling Well", "Grandmother's Map",
        "The Runaway Cart", "Songs of the Sea", "The Paper Boat",
    ]


@pytest.mark.asyncio
async def test_catalog_search(client):
    headers = await admin_headers()
    await client.post("/admin/catalog/publish", headers=headers)

    vheaders = await viewer_headers()

    async def search(**params):
        resp = await client.get("/catalog/search", params=params, headers=vheaders)
        assert resp.status_code == 200
        return resp.json()

    # 'kite' matches shows + episodes titled "The Lost Kite" across shows.
    data = await search(q="kite")
    assert data["total"] > 0

    # Filters compose: same query restricted to Hindi variants still matches.
    data = await search(q="kite", language="hi")
    assert data["total"] > 0
    langs = {lang for show in data["results"] for season in show["seasons"]
             for ep in season["episodes"] for lang in ep["languages"]}
    assert "hi" in langs

    # Section filter restricts to the songs rail.
    data = await search(section="songs")
    assert data["total"] == 2  # Peblo Songs + Peblo Songs - Lyrical
    assert all(r["section"] == "songs" for r in data["results"])

    # No match returns an empty list, not an error.
    data = await search(q="zzzzz-no-such-thing")
    assert data["total"] == 0
