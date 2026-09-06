# Peblo TV Mini 🎬

A full-stack, production-grade miniature streaming product:
- **Admin CMS**: Internal content team portal to manage shows, upload validated artwork/videos, and trigger single-click catalogue publishing.
- **FastAPI + PostgreSQL Backend**: Async Python service handling data normalization, role enforcement, media validation, storage abstraction, and atomic publishing pipelines.
- **Viewer App**: Child-facing consumer streaming UI with Netflix-style profiles, category section rows, live search, and HTML5 video playback.

---

## 🚀 How to Run It

### Option A: Quickstart via Docker Compose (Recommended)

```bash
docker-compose up --build
```

This spins up four services out of the box:

| Service | Local URL | Description |
|---|---|---|
| **API Backend** | `http://localhost:8000` | FastAPI app (`/docs` for Swagger UI, `/health` for status) |
| **CMS Portal** | `http://localhost:3000` | Admin & Editor management dashboard |
| **Viewer App** | `http://localhost:3001` | Consumer streaming application |
| **PostgreSQL 16** | `localhost:5432` | Relational database (`peblo_tv`) |

> **Out-of-the-Box Experience**: On initial boot, the backend automatically seeds the database with 95 catalog items, generates spec-compliant placeholder artwork & playable media clips for all published episodes, and auto-publishes the initial `catalogue.json`. The viewer is populated instantly upon first launch!

#### Demo Credentials:
- **CMS Admin**: `admin@peblo.tv` (Full publish & management access)
- **CMS Editor**: `editor@peblo.tv` (Show & media edit access)
- **Viewer Auth**: `kids@peblo.tv` / `peblo123` or `family@peblo.tv` / `peblo123`

---

### Option B: Local Development Setup (Without Docker)

#### Prerequisites
- **Python 3.10+** (3.12 recommended)
- **Node.js 18+** & **npm**
- **PostgreSQL 16** (running locally or via Docker)

#### 1. Backend Setup
```bash
cd backend
python -m venv .venv
# On macOS/Linux: source .venv/bin/activate
# On Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp ../.env.example .env

# Run database migrations & seed automatically on startup
uvicorn app.main:app --reload --port 8000
```

#### 2. CMS Frontend Setup
```bash
cd ../cms
npm install
npm run dev # Starts on http://localhost:3000
```

#### 3. Viewer Frontend Setup
```bash
cd ../viewer
npm install
npm run dev # Starts on http://localhost:3001
```

#### 4. Running Backend Automated Tests
```bash
cd ../backend
python -m pytest tests/ -v
```

---

## 🏛️ Decisions and Trade-offs

1. **Decoupled Architecture**: Separated the API, Admin CMS, and Consumer Viewer into standalone services. This guarantees that internal content editing or publish workflows never degrade consumer video playback performance.
2. **Pre-published Catalogue Snapshot**: Rather than hitting PostgreSQL for every consumer browse/search request, publishing renders a single versioned `catalogues/catalogue.json` static snapshot. This eliminates relational JOIN overhead and enables CDN edge caching.
3. **Server-Side Enforcement of Role-Based Security**: Role permissions (`admin`, `editor`, `viewer`) are verified strictly at the API layer via JWT tokens (`backend/app/core/auth.py`). The viewer app enforces authentic authentication (Netflix-style login is mandatory before accessing catalog routes).
4. **Abstracted Multi-Backend Storage**: Built a pluggable storage interface enabling seamless transitions between local disk storage and cloud storage (Cloudflare R2) via simple environment variable flags (`STORAGE_BACKEND`).
5. **Self-Contained Local Testability**: Built synthetic SVG artwork and HTML5 playable video clip generators into the seed process, enabling complete visual testing without requiring external S3/Cloudflare credentials upfront.

---

## ⏱️ Time Breakdown (Approximate)

| Part / Feature Area | Hours Spent | Key Tasks Completed |
|---|---|---|
| **Data Modeling & Seed Normalization** | ~5.0 hours | Schema design (Shows, Seasons, Episodes, Artworks, PublishRun), handling content groups, language variants, and seed issue reporting. |
| **Publish Pipeline & Atomicity** | ~4.5 hours | Validation engine, snapshot builder, atomic `os.replace` file writing, audit logs. |
| **Backend API & Storage Abstraction** | ~4.0 hours | Storage interface (`LocalStorage` & `R2Storage`), video streaming with HTTP Range support, role-gated routes. |
| **Admin CMS Portal (React + Vite)** | ~4.5 hours | Show editor, artwork upload validation feedback, episode listing, 1-click publish flow. |
| **Consumer Viewer App (React + Vite)** | ~3.5 hours | Hero video banner, section carousels, search & filter interface, HTML5 video player modal. |
| **Testing, CI & Documentation** | ~2.5 hours | Pytest automated test suite, GitHub Actions workflow (`ci.yml`), comprehensive README. |
| **Total** | **~24.0 hours** | |


---

## 📝 Part E — Written Answers

### 1. How you made publishing atomic — and what happens if the process dies mid-publish?

#### **Atomic Publishing Architecture**
Publishing (`POST /admin/catalog/publish`) transforms normalized database entities into a public JSON asset through a multi-stage atomic pipeline (`backend/app/services/publish.py`):

1. **Validation Gate**: Before mutating disk state or database status, `get_validation_issues(db)` validates all shows and episodes against structural rules (missing posters, missing thumbnails, unassigned sections). If any blocking issue is detected, the run aborts immediately with `outcome = failed` and zero file changes occur.
2. **Versioned Copy Generation**: A timestamped versioned backup (`catalogues/catalogue-{run_id}.json`) is saved first for auditability and rollback support.
3. **Atomic File Replacement (`os.replace`)**: The live file `catalogues/catalogue.json` is updated via a temporary file write pattern:
   - Data is written to `catalogues/catalogue.json.tmp`.
   - OS file buffers are explicitly flushed and synchronized to physical disk using `f.flush()` followed by `os.fsync(f.fileno())`.
   - `os.replace(tmp_path, live_path)` executes an atomic filesystem rename operation.

#### **What happens if the process dies mid-publish?**
- **Crash before `os.replace`**: The temporary file `catalogue.json.tmp` or versioned file may remain on disk, but the live `catalogue.json` is completely untouched. Concurrent or new viewer requests continue receiving the previous 100% valid catalogue snapshot.
- **Crash during `os.replace`**: On POSIX filesystems and modern NTFS on Windows, `rename()` / `replace()` is an atomic directory table mutation. A reader opening `catalogue.json` will observe **either** the full old catalogue **or** the full new catalogue—never a corrupt, partially-written JSON file.
- **Crash after file swap but before DB transaction commit**: The new catalogue is live on disk and immediately served to viewers. The database `PublishRun` record will remain marked as incomplete. On the subsequent publish invocation, the pipeline runs cleanly and reconciles `PublishRun.is_current`.

---

### 2. Your storage abstraction: what changes to move from local disk to Cloudflare R2?

#### **Current Abstraction**
All media and JSON persistence is routed through `StorageBackend` (`backend/app/services/storage.py`), an abstract base class enforcing standard async methods: `save_file()`, `get_file_url()`, `save_json()`, `read_json()`, and `delete_file()`.

- `LocalStorage`: Reads/writes files from the local filesystem (`/app/storage`).
- `R2Storage`: Interacts directly with Cloudflare R2 via `boto3` (S3-compatible API).

#### **Required Changes to Switch to Cloudflare R2**
1. **Configuration Shift**: Update environment variables in `.env` without modifying application code:
   ```env
   STORAGE_BACKEND=r2
   R2_ACCOUNT_ID=your_cloudflare_account_id
   R2_ACCESS_KEY_ID=your_access_key
   R2_SECRET_ACCESS_KEY=your_secret_key
   R2_BUCKET_NAME=peblo-tv-assets
   ```
2. **URL Resolution**: `get_file_url(path)` dynamically transitions from local endpoint routes (`/storage/...`) to Cloudflare R2 public bucket endpoints or custom CDN domains (`https://cdn.peblo.tv/...`).
3. **S3 Key-Level Atomicity**: Uploading `catalogues/catalogue.json` to Cloudflare R2 via `put_object()` is atomic at the object key level.
4. **CDN Cache Purging**: When pairing Cloudflare R2 with Cloudflare CDN, the `publish_catalogue` service can trigger a Cloudflare Cache Purge API call or include HTTP `Cache-Control` revalidation headers (`max-age=60, stale-while-revalidate=300`) to propagate updates across global edge nodes instantly.

---

### 3. Search: how did you implement it, at what catalogue size does it stop working, and what would you do next?

#### **Current Implementation**
`GET /catalog/search` (`backend/app/routers/catalog.py`) operates directly over the published catalogue snapshot:
1. Reads `catalogues/catalogue.json` into memory.
2. Filters across section hierarchies (`sections` -> `shows` -> `seasons` -> `episodes`).
3. Evaluates substring match `q` against show titles, synopses, categories, and individual episode titles/synopses, alongside composite filters (`category`, `language`, `section`).

#### **At what catalogue size does it stop working?**
- **Breakdown Threshold**: ~1,000 to 5,000 shows (~50,000 episodes, resulting in a ~10MB - 50MB static JSON snapshot).
- **Bottlenecks**:
  1. **CPU & Memory Overhead**: Deserializing a multi-megabyte JSON string on every search HTTP request saturates worker CPU threads.
  2. **O(N × M) Time Complexity**: Nested iteration over every show, season, and episode per search request creates extreme latency under concurrent load.
  3. **No Fuzzy/Typo Tolerance**: Standard substring checks (`q in title`) fail on user typos (e.g. searching "peblo" vs "pebloo").

#### **What to do next?**
1. **In-Memory Cache Index (Short-Term)**: Load `catalogue.json` into process memory at startup and rebuild an inverted index in RAM upon publish events, reducing search time to O(1) keyword lookups without re-parsing JSON per request.
2. **PostgreSQL Full-Text Search (Medium-Term)**: Leverage Postgres `tsvector`, `tsquery`, and `pg_trgm` GIN indexes over `shows` and `episodes` tables for fast indexed searching with relevance scoring.
3. **Dedicated Search Engine (Long-Term)**: Push the published catalogue snapshot to **Meilisearch** or **Typesense** during the publish pipeline. This delivers sub-5ms typo-tolerant search, faceted filtering, and multi-language stemming at scale.

---

### 4. Why serve a pre-published catalogue file at all instead of querying the database per request? Where does that choice bite you?

#### **Why serve a pre-published catalogue file?**
- **Read-Heavy Workload Optimization**: Consumer streaming apps exhibit an extreme 1,000:1 read-to-write ratio. Pre-rendering the entire catalogue snapshot isolates PostgreSQL from viewer traffic spikes.
- **Zero-DB Load for Viewers**: Viewer browsing requests hit static file storage or CDN edge caches directly, executing zero SQL queries or relational JOINs across `shows`, `seasons`, `episodes`, and `artworks`.
- **Global CDN Caching**: A static JSON asset can be cached globally across edge nodes (Cloudflare/CloudFront), yielding sub-20ms latency worldwide.
- **Editorial Control & Curated Releases**: Admins can prepare complex multi-show content updates in draft state without exposing incomplete changes to consumers until "Publish Catalogue" is triggered.

#### **Where does that choice bite you?**
1. **Propagation Lag / Lack of Instant Real-Time Edits**: Emergency fixes (e.g., removing copyrighted content or fixing a typo) require triggering a publish run and invalidating CDN caches.
2. **Dynamic / Personalized Content Limitations**: User-specific data (e.g. "Continue Watching" progress, watchlists, personalized recommendations, regional licensing) cannot exist in a shared static JSON file and must be fetched via separate dynamic user endpoints.
3. **Monolithic Payload Growth**: As the catalog expands to tens of thousands of shows, a single `catalogue.json` file becomes too large to download over mobile network connections, forcing architectural split into paginated section files (e.g., `catalogues/home.json`, `catalogues/shows/show-123.json`).

---

### 5. What you left out and why. Which AI tools you used, and where you accepted or rejected their output.

#### **What was left out and why**
- **HLS/DASH Video Transcoding Segmenter**: Implemented standard MP4 video streaming with HTTP `Accept-Ranges` byte-range support for video seeking rather than generating multi-bitrate HLS `.m3u8` playlists via `ffmpeg`, keeping local dependencies minimal while proving video streaming capability.
- **Complex OAuth2 / SSO Providers**: Used JWT tokens with role scopes (`admin`, `editor`, `viewer`) to fulfill mandatory server-side authentication without requiring external auth provider dependencies.
- **Alembic DB Migrations**: Applied schema creation via SQLAlchemy `create_all()`. For a multi-developer production environment, explicit versioned Alembic migration scripts would be added.

#### **AI Tools Used & Engineering Judgment**
- **Tools Used**: Gemini 3.6 Flash / ChatGPT for initial Pydantic schema scaffolding, CSS flexbox/grid layout structures, and Vite component boilerplates.
- **Accepted Output**: Pydantic schema validation structures, standard async SQLAlchemy session management patterns, and CSS responsive layout grids.
- **Rejected Output**:
  1. *Direct DB querying in viewer routes*: AI initially suggested querying SQLite/PostgreSQL directly for `/catalog` and `/catalog/search`. **Rejected** to enforce the core architectural constraint of serving a pre-published static catalogue snapshot.
  2. *Naive file write for publishing*: AI generated simple `open('catalogue.json', 'w').write(...)`. **Rejected** because a process crash mid-write would corrupt the live catalogue. Replaced with atomic temporary file creation, `os.fsync`, and atomic `os.replace`.
  3. *Heavy external runtime dependencies*: AI suggested invoking `ffmpeg` subprocesses on every backend boot. **Rejected** in favor of self-contained, lightweight synthetic SVG and MP4 generator utilities for instant, zero-dependency local setup.

---

## 📽️ Screen Recording & Flow Walkthrough

The core user workflows demonstrated in the application:
1. **CMS Login & Dashboard**: Sign in as `admin@peblo.tv` at `http://localhost:3000`.
2. **Show & Episode Management**: Inspect shows, upload poster/banner artwork with instant aspect ratio & file size validation feedback.
3. **Media & Video Upload**: Upload video files for episode content groups.
4. **Validation Report & 1-Click Publish**: View green/blocking validation reports and trigger catalogue publish.
5. **Viewer App Login & Browse**: Log into `http://localhost:3001` as `kids@peblo.tv`.
6. **Hero Banner & Section Carousels**: Browse featured shows, minisodes, and categories.
7. **Live Search & Detail View**: Perform instant search by title/category/language and stream episode video clips via the built-in player.
