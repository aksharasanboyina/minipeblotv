from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import engine, init_db
from app.routers import admin, auth, catalog
from app.seed import seed as seed_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.SEED_ON_START:
        try:
            await seed_data()
        except Exception as e:
            print(f"Seeding warning: {e}")
    yield
    await engine.dispose()


app = FastAPI(title="Peblo TV Mini API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(catalog.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "peblo-tv-mini-api"}


storage_dir = Path(settings.STORAGE_LOCAL_PATH)
storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")