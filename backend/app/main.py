import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, TimeoutError as SATimeoutError

from app.api import api_router
from app.config import get_settings
from app.core.timezone import (
    POSTING_TIMEZONE,
    italy_now_display,
    italy_now_iso,
    italy_utc_offset,
)
from app.database import check_database_connection, invalidate_pool
from app.db_async import run_sync
from app.services.scheduler import start_scheduler, stop_scheduler
from app.startup_db import run_blocking_startup

# Import sources to register them
import app.sources.facebook  # noqa: F401
import app.sources.autoscout24  # noqa: F401
import app.sources.tutti  # noqa: F401
import app.sources.ricardo  # noqa: F401
import app.sources.anibis  # noqa: F401

logging.basicConfig(level=logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
settings = get_settings()

DB_STARTUP_TIMEOUT_SECONDS = 60
DB_STARTUP_ATTEMPTS = 3


async def _connect_database_with_retries(app: FastAPI) -> bool:
    for attempt in range(1, DB_STARTUP_ATTEMPTS + 1):
        label = "initial" if attempt == 1 else f"retry {attempt - 1}/{DB_STARTUP_ATTEMPTS - 1}"
        logger.info("Startup: database %s (max %ss)...", label, DB_STARTUP_TIMEOUT_SECONDS)
        try:
            await asyncio.wait_for(
                asyncio.to_thread(run_blocking_startup, settings),
                timeout=DB_STARTUP_TIMEOUT_SECONDS,
            )
            app.state.db_ready = True
            logger.info("Startup: database ready")
            return True
        except asyncio.TimeoutError:
            invalidate_pool()
            logger.warning("Startup: database timed out (%ss)", DB_STARTUP_TIMEOUT_SECONDS)
        except Exception as exc:
            invalidate_pool()
            logger.warning("Startup: database error: %s", exc)
        if attempt < DB_STARTUP_ATTEMPTS:
            await asyncio.sleep(2 * attempt)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_ready = False

    if not await _connect_database_with_retries(app):
        logger.error("Startup: database unavailable — login and dashboard will return 503 until DB works")

    try:
        start_scheduler()
    except Exception as exc:
        logger.warning("Startup: scheduler not started: %s", exc)

    logger.info("Application ready")
    yield
    stop_scheduler()
    logger.info("Application shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(OperationalError)
async def database_unavailable_handler(_request: Request, exc: OperationalError):
    invalidate_pool()
    logger.warning("Database unavailable: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database connection failed. Check internet connection and try again."},
    )


@app.exception_handler(SATimeoutError)
async def database_pool_timeout_handler(_request: Request, exc: SATimeoutError):
    invalidate_pool()
    logger.warning("Database pool timeout: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database busy — please wait a moment and try again."},
    )


@app.get("/health")
async def health_check(request: Request):
    db_ready = getattr(request.app.state, "db_ready", False)
    if not db_ready:
        return {
            "status": "starting",
            "database": "connecting",
            "ready": False,
            "version": settings.APP_VERSION,
        }
    try:
        db_ok = await run_sync(check_database_connection, timeout=5)
    except asyncio.TimeoutError:
        db_ok = False
        invalidate_pool()
    italy_now = italy_now_iso()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "ready": db_ok,
        "version": settings.APP_VERSION,
        "timezone": POSTING_TIMEZONE,
        "utc_offset": italy_utc_offset(),
        "italy_now": italy_now,
        "italy_now_display": italy_now_display(),
        "schedule_note": "All schedule_date + schedule_time values use Europe/Rome (Italy), not UTC or your PC clock.",
    }
