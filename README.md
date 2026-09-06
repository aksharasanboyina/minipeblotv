# Peblo TV Mini

A miniature of Peblo's streaming product: an internal **CMS** uploads a show's episodes and artwork → a **FastAPI + PostgreSQL** backend builds a **published catalogue.json** → a child-facing **viewer UI** reads that catalogue to browse rows, search, and filter — Netflix-style.

**Stack:** FastAPI (async) + PostgreSQL + SQLAlchemy 2.0 · React 19 + TypeScript + Vite · TanStack Query · Docker Compose · GitHub Actions

---

## Run it (docker-compose)

```bash
docker-compose up --build
```

This brings up four services, each seeded and working:

| Service | URL | Notes |
|--------|-----|-------|
| API (FastAPI) | http://localhost:8000 | `/docs` for Swagger, `/health` for health |
| CMS | http://localhost:3000 | content team UI |
| Viewer | http://localhost:3001 | child-facing browse UI |
| Postgres 16 | localhost:5432 | `peblo` / `peblo_secret` / `peblo_tv` |

The DB is seeded from `backend/seed_shows.json` on first boot: **95 rows across 8 shows → 94 imported**. The one row that doesn't make it in is a deliberate duplicate-language-variant imperfection (see "What the seed is hiding"). Because the challenge's artwork assets are not bundled, the boot also **generates spec-conforming placeholder artwork** for every published show (poster + banner) and episode (thumbnail), plus **playable placeholder MP4 clips** for every episode (via ffmpeg, installed in the API image), then **auto-publishes the initial catalogue** — so the viewer has content out of the box.

Demo sign-ins: **CMS** — `admin@peblo.tv` (role `admin`) or `editor@peblo.tv` (role `editor`). **Viewer** — a Netflix-style sign-in screen at `:3001` (email + password): `kids@peblo.tv` / `peblo123` (or `family@peblo.tv`). Upload real artwork/videos through the CMS to replace placeholders (an upload overwrites that slot).

### Run without Docker (for development)

```bash
# 1. A Postgres must be running; point DATABASE_URL at it
cd backend
python -m venv .venv && . .venv/bin/activate    # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env                          # adjust DATABASE_URL host -> localhost
uvicorn app.main:app --reload --port 8000

# 2. Frontends (separate terminals)
cd ../cms  && npm install && npm run dev        # :3000
cd ../viewer && npm install && npm run dev      # :3001

# 3. Backend tests (an empty Postgres database is required; tests create tables + seed themselves)
cd ../backend
DATABASE_URL=postgresql+asyncpg://peblo:peblo_secret@localhost:5432/peblo_tv_test \
STORAGE_LOCAL_PATH=./storage SEED_ON_START=false \
python -m pytest tests/ -v
```

> Python 3.12 is the supported runtime (used in the Docker image). Some pinned native wheels (`pydantic-core`, `asyncpg`, `Pillow`) don't yet build on Python 3.14 locally — use 3.12 or Docker.

---

## Security model (roles, actually enforced)

Auth is a simple JWT issuer (`POST /auth/token`). A demo issuer returns tokens for `editor` and `admin`; in production this would sit behind SSO/OAuth (see Secrets).

- **editor** — read + write shows/seasons/episodes, upload artwork + videos, view validation.
- **admin** — everything editors can do **plus** `POST /admin/catalog/publish` and deleting videos.
- **viewer** — the child-facing app's own accounts (`POST /auth/viewer/token`, email + password). Viewer tokens unlock `/catalog`, `/catalog/search`, `/catalog/shows/{slug}` and video streaming — no viewer token, no catalogue (Netflix-style login is enforced server-side, not just cosmetic). Because an HTML `<video>` can't send headers, the stream endpoint also accepts `?token=...`, validated identically.

Roles are enforced **server-side** on every route via a dependency (`require_role(...)` / `require_viewer_role(...)` in `backend/app/core/auth.py`). The CMS simply hides the publish button for editors, but the enforcement is at the API — an editor who calls the publish endpoint by hand gets `403`, not a client-only gate. Verified by `tests/test_api.py::test_editor_cannot_publish`.

---

## Data model

`shows → seasons → episodes`, plus `artworks` (belong to a show or an episode) and `publish_runs`.

Postgres tables (`backend/app/models/models.py`):

- **shows** — title, slug (unique), section, categories (JSON), synopsis, status.
- **seasons** — unique `(show_id, season_number)`.
- **episodes** — belongs to a season, has `episode_number`, `title`, `duration_seconds`, `language`, `content_group`, `synopsis`, `status`.
- **artworks** — `artwork_type` (poster/banner/thumbnail), file path, dimensions, size; FK to show or episode.
- **publish_runs** — who, when, outcome, counts, catalogue path, `is_current` flag.

**Indexes / constraints** (see `__table_args__` on each model):
- `UNIQUE (show_id, season_number)` — one season number per show.
- `UNIQUE (content_group, language)` — **the** hard rule: one language variant per episode group. This enforces the `content_group` convention at the database level.
- `UNIQUE (season_id, episode_number, language)` — no duplicate (S,E,lang) within a season.
- `INDEX (content_group)` — the grouping key used throughout publish.
- `INDEX (shows.slug)` — lookups by slug from the viewer.

Migrations are applied via `Base.metadata.create_all` on startup (SQLAlchemy). For a production system I'd move to **Alembic** — noted in what I left out.

---

## The publish pipeline (Part A core)

`POST /admin/catalog/publish` (admin only) runs `app/services/publish.py`:

1. **Validate** — compute the blocking/warning report (`get_validation_issues`). If any blocking issue exists, the run is recorded with `outcome=failed` and returns 422.
2. **Build** — `build_catalogue` walks published shows, groups episodes by `content_group` within each season into **one entry with a `languages` list**, keeps the ordering by section (`featured → series → minisodes → songs`), and moves **Season 0 to a trailer field** (never a normal season).
3. **Write atomically** — the catalogue JSON is written to a **versioned** file (`catalogues/catalogue-<run_id>.json`) and then to the **live** `catalogues/catalogue.json` via a temp-file + `os.replace()` (see below).
4. **Record** — a `publish_run` row captures who, when, show/episode counts, and outcome; the previous `is_current` run is demoted and the new one marked current.

**Atomicity.** `catalogue.json` is written to `catalogue.json.tmp`, flushed, `fsync`ed, then `os.replace()`d onto the live path. Rename on the same filesystem is atomic, so a reader (the viewer, or `GET /catalog`) **never observes a half-written file** — they see either the old complete catalogue or the new complete one. If the process dies mid-write, it dies writing the temp file; the live `catalogue.json` is untouched and still valid. On restart, an orphaned `.tmp` file is simply ignored/overwritten on the next publish.

**Idempotent.** Running publish twice with unchanged data produces the same logical catalogue; each run just writes a new versioned file and flips `is_current`.

---

## Placeholder artwork & the out-of-the-box catalogue

A fresh seed contains **no real image files** (the `assets/` folder from the challenge is empty), so without help the validator would block every published show and episode and nothing could ever be published. On every boot, `app/services/placeholder_art.py` provisions **generated JPEGs that meet the exact same server-side specs the upload endpoint enforces** (correct dimensions, aspect ratio within tolerance, under 200 KB) for any published entity still missing artwork — shows get poster + banner, published episodes get a thumbnail (ep_0036 included). Idempotent: real CMS uploads are never overwritten, because provisioning only fills gaps.

Then, when no live `catalogues/catalogue.json` exists yet and validation is green, the boot **auto-publishes once** (recorded as a `publish_runs` row by `seed-boot`), so the viewer has content out of the box. Every later publish is admin-driven from the CMS Publish tab.

Uploading real artwork **replaces** the placeholder for that slot (`POST /admin/artwork/...` deletes the previous image of the same type first) — the CMS show editor exposes poster/banner/thumbnail slots for shows and a thumbnail uploader per episode row, so the editor can swap in real art and re-publish without leaving the UI.

---

## Artwork upload & validation (Part A, 15 pts)

`POST /admin/artwork/{entity_type}/{entity_id}?artwork_type=poster|banner|thumbnail` validates **server-side** against `reference.json`:

| type | aspect | target px | max |
|------|--------|-----------|-----|
| poster | 2:3 | 600×900 | 200 KB |
| banner | 16:9 | 1280×720 | 200 KB |
| thumbnail | 16:9 | 640×360 | 200 KB |

`app/services/artwork.py` rejects on: wrong aspect ratio (tolerance ±5%), dimensions too far off target, and **file size over 200 KB**. Errors are written for a non-technical editor, e.g.:

> *"File size 412 KB exceeds the 200 KB limit for banner. Please compress the image or use a smaller file."*
> *"Aspect ratio mismatch for poster: expected ~600x900 (ratio 0.67), got 900x900 (ratio 1.00). Please upload an image with the correct aspect ratio."*

Note there is **no client-side-only validation** — the browser gives immediate feedback, but the source of truth is the API.

**Storage is abstracted** behind `app/services/storage.py` with an interface (`save_file`, `get_file_url`, `save_json`, `read_json`, `delete_file`). Two implementations:
- `LocalStorage` (default, docker volume).
- `R2Storage` (Cloudflare R2 via boto3, S3-compatible) — swap by setting `STORAGE_BACKEND=r2` + R2 credentials. **To move to R2 you change config, not code.**

---

## Video upload & playback (real media)

Episodes stream through `GET /catalog/video/{episode_id}` (viewer-gated, Range-aware so seeking works). Videos live **per content group**, so all language variants of an episode share one file.

Editors upload real media in the CMS show editor (each episode row has a video control) or via the API:

- `POST /admin/videos/{episode_id}` (editor/admin) — upload MP4/WebM. The file is **probed with ffprobe** when available and rejected with a readable error if it isn't playable video; the previous video is only replaced after the new one validates (no data loss on a bad upload). Size limit 250 MB.
- `GET /admin/videos/{episode_id}` — current video state (ext, size).
- `DELETE /admin/videos/{episode_id}` (admin only).

On a fresh boot, ffmpeg generates a **playable placeholder clip** per published episode (see "Placeholder artwork & the out-of-the-box catalogue" below) so nothing is unwatchable; a real upload simply replaces it. After any media change, re-publish from the CMS Publish tab — `build_catalogue` only advertises `has_video`/`video_url` for episodes whose file actually exists.

---

## Search (viewer)

`GET /catalog/search?q=&category=&language=&section=` runs server-side over the published catalogue: `q` matches show title, episode title, and categories; all filters **compose**.

**Scale reasoning.** Today the catalogue is a few hundred KB and search is an in-memory scan of the JSON — fast enough (well under a millisecond) at this size. On a cheap cloud function a single ~1 MB catalogue scan is still ~1 ms. It *stops* being fine somewhere around a few thousand entries / multi-MB catalogue, or once we want ranked or typo-tolerant results. The next step is to ship the catalogue into **Postgres** (or a real search index) and query it with FTS/trigram, so search scales and doesn't re-parse JSON per request. This is documented and reasoned in Part E.

---

## Why a pre-published file at all?

The catalogue is materialised once on publish and served as a static file, rather than the viewer querying the DB per request. **Why:** the viewer traffic is read-heavy and child-facing; serving one static JSON from object storage/CDN is fast, cheap, cacheable at the edge, and avoids hammering Postgres with N joins per browse. The publish job is the write path; the viewer never touches the source of truth.

**Where it bites:** 
- **Eventual consistency** — a viewer won't see edits until the next publish (that's by design, but you must be comfortable with publish-time freshness).
- **No per-request derivation** — anything you forget to bake into the catalogue (new filter facets, computed fields) requires a re-publish.
- **Version skew / drift** — the stored JSON can drift from the DB if a publish silently fails; mitigated by recording runs and back-filling from the DB on miss.

---

## Part E — Written answers (as requested)

**Atomic publishing & mid-publish death** — see the pipeline section above: temp-file + `os.replace` + fsync; a crash mid-publish leaves the live file valid and only an orphaned `.tmp`.

**Storage abstraction → Cloudflare R2** — implement `R2Storage` (already done) using the same interface; swap `STORAGE_BACKEND=r2` and set the four R2 env vars; no caller changes. The only behavioural difference is that `save_json`/`read_json` now hit the bucket, and object URLs become public bucket URLs instead of `/storage/...`.

**Search implementation & scale** — in-memory scan of the parsed catalogue; works to roughly a few thousand entries; next step is Postgres FTS/trigram or a dedicated index keyed off the same catalogue.

**Why pre-published file vs per-request DB query** — see above.

**What I left out, and why:**
- **Alembic migrations** — used `create_all` for simplicity; a real deploy needs versioned migrations.
- **Full episode CRUD UI in the CMS** — the API has full CRUD + the validation surfaces the data issues; the CMS edit screen focuses on the show + artwork, and every episode row has a thumbnail uploader (episode-level *editing* of title/duration/etc. is reachable via the API/OpenAPI).
- **Real SSO / PBAC groups** — demo JWT issuer only.
- **Optional stretch items** (versioned rollback exists as versioned files + `is_current`, but no UI rollback button; no dry-run diff; no per-field audit log) — intentionally skipped to keep the core honest and shippable.

**AI tools.** I used an AI coding assistant to scaffold both the backend and the two frontends and to draft the README reasoning. I accepted its structure but **re-wrote/reviewed the security boundaries (role enforcement), the atomic publish path, and the data-issue handling by hand** — those are the parts where correctness matters most and where I did not take generated code on trust. I rejected the assistant's initial storage layer (it hard-coded local disk) and replaced it with the abstracted interface, and I fixed the seed to surface duplicate-language-variant imperfections rather than silently crashing.

**What the seed is hiding (validation findings).** Two deliberate imperfections in the source data, recorded in `data_issues.json` and surfaced by the validator as **warnings** (never blockers, so they can't dead-end publishing):
1. **`ep_9001`** — a **duplicate language variant**: content_group `motis-many-lives-s01e02` has *two* `hi` episodes (`ep_0004` and `ep_9001`). This breaks the `(content_group, language)` uniqueness rule. The seed keeps the first (`ep_0004`) and records `ep_9001` in `data_issues.json` (`seed_skipped`), which the validation report surfaces as a **warning** with fix guidance. The row never entered the database — the `(content_group, language)` unique constraint rejected it at import — so there is nothing to unpublish or delete in the CMS; the source file (`backend/seed_shows.json`) must be fixed and the DB re-seeded.
2. **`ep_0036`** — the dataset's deliberately art-less episode: its row declares `artwork_available: []` while published. It is imported (the validator's rules apply to live DB content, not to declared intentions), gets a generated placeholder thumbnail so the catalogue can ship, and is recorded in `data_issues.json` (`seed_notes`) with a note to upload real artwork before launch.

The validator's teeth stay real in the other direction: it recomputes from **live DB content**, so any published episode that loses its thumbnail (or a new published episode added without one) is a blocking issue with an editor-actionable message until a real upload — through the CMS or `POST /admin/artwork/episode/{id}` — clears it. That flow is covered by `tests/test_api.py::test_validation_blocks_missing_artwork_and_upload_resolves`, and the fresh-boot, green, auto-published state by `test_boot_state_is_publishable_out_of_the_box`.

The validation report (`GET /admin/validation-report`) groups everything by entity with editor-actionable messages — that's the page the CMS Publish tab shows, and it drives the publish-button-with-reasons UX.

---

## Operability

- **Health:** `GET /health`.
- **Alerting:** I'd alert on **publish failures** (`publish_runs.outcome = failed` where `started_at` is recent). Reasoning: a failed publish silently means the viewer keeps serving stale content — the highest-impact silent failure in this design. Alert on the count of failed runs in the last 15 minutes.
- **Secrets in production:** never commit `.env`. Manage `JWT_SECRET_KEY`, R2/crypto keys, and DB credentials via a **secrets manager** (e.g. AWS Secrets Manager / GCP Secret Manager / Vault) injected as env vars at deploy time, rotate on a schedule, and restrict each service to a minimal IAM role. R2 access keys should be scoped to only the catalogue bucket. `JWT_SECRET_KEY` must be a long random value, regenerated and rotated — not a default.

### CI (GitHub Actions, `.github/workflows/ci.yml`)
Lint (`ruff`), backend tests, and **TypeScript typecheck + production build** for both frontends run on every push/PR. A **Docker build** job builds all three images. The **deploy** job is written and explained (it steps through: push images to GHCR → deploy to Fly/Render/ECS → run migrations → smoke-test `/health` and `/catalog`) but does not run against a real cloud you don't have.

---

## Project layout

```
.
├── backend/            FastAPI app
│   ├── app/
│   │   ├── core/       config, database, auth (role enforcement)
│   │   ├── models/     SQLAlchemy models
│   │   ├── routers/    admin (CRUD/publish), catalog (viewer), auth
│   │   ├── schemas/    Pydantic request/response models
│   │   └── services/   storage (abstracted), artwork validation, placeholder art, placeholder/uploaded videos, publish
│   ├── app/seed.py     seeds DB, provisions placeholder art + clips, auto-publishes once, records data issues (reads seed_shows.json)
│   ├── tests/          risky-part tests (roles, publish, search)
│   └── requirements.txt
├── cms/                React + TS content team UI (port 3000)
├── viewer/             React + TS child-facing browser (port 3001)
├── assets/             sample artwork placeholders (see note below)
├── .github/workflows/  CI + documented deploy
├── docker-compose.yml
└── .env.example
```

> **`assets/`**: the prompt references sample images (`thumb_good.jpg`, `poster_wrong_ratio.jpg`, `banner_too_big.png`, …). Those binary files were not present in the working directory I was given, so I couldn't bundle them. They aren't needed to reach a populated viewer — the boot provisions spec-conforming placeholder artwork instead (see "Placeholder artwork"). The validation path is still demonstrable: upload a wrongly-sized or oversized file through any CMS upload slot and it is rejected with the human-readable errors above.

---

## Time spent (approx)

| Part | Time |
|------|------|
| Backend (models, CRUD, publish, auth, storage, validation) | ~2.5 h |
| Search & catalog endpoints | ~45 m |
| Tests on risky parts | ~40 m |
| CMS (React) | ~1.5 h |
| Viewer (React) | ~1 h |
| Compose / CI / .env / docs | ~1 h |
| **Total** | **~7 h** |
