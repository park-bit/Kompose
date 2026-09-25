import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine, Base
from app.cache import close_redis
from app.routes import router
from app.settings_routes import router as settings_router
from app.settings_routes import _apply_to_env, _load_saved_keys

# Apply any user-saved keys before settings are first read
_apply_to_env(_load_saved_keys())


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logging.info("Database tables verified.")
    except Exception as exc:
        logging.warning("Database init note: %s", exc)
    yield
    await close_redis()


app = FastAPI(
    title="Travel Planner API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(settings_router)



@app.get("/health")
async def health():
    return {"status": "ok"}
