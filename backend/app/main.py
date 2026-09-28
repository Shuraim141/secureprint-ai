"""SecurePrint AI: FastAPI application entry point."""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from app.api import audit as audit_api
from app.api import auth as auth_api
from app.api import dashboard as dashboard_api
from app.api import designs as designs_api
from app.api import health as health_api
from app.api import quality as quality_api
from app.api import supply_chain as supply_chain_api
from app.audit.logger import write_audit
from app.config import get_settings
from app.database import SessionLocal, init_db
from app.hardware import get_hardware_profile
from app.logging_config import setup_logging
from app.models.user import RevokedToken
from app.services.seed import seed_roles
from app.timeutil import utcnow

settings = get_settings()
logger = logging.getLogger("secureprint")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging(settings.log_level)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    profile = get_hardware_profile(settings.hardware_profile)
    with SessionLocal() as db:
        seed_roles(db)
        db.execute(delete(RevokedToken).where(RevokedToken.expires_at < utcnow()))
        db.commit()
        write_audit(db, action="SYSTEM_STARTUP", user="system", resource="api",
                    details={"environment": settings.environment, "hardware_profile": profile.name})
    logger.info("startup", extra={"ctx": {
        "environment": settings.environment, "hardware_profile": profile.name,
        "cpu_cores": profile.cpu_cores, "ram_gb": profile.ram_gb}})
    yield
    logger.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    description="AI-driven 3D/4D printing security platform (academic MVP).",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,  # bearer tokens travel in the Authorization header, not cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Request id, timing log (path only, never query strings/bodies) and security headers."""
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    too_large = False
    if request.method in {"POST", "PUT", "PATCH"} and request.url.path.startswith("/api/designs"):
        # Early refusal from the declared size, before the body is buffered to disk.
        # (Chunked uploads without Content-Length are still capped while being read.)
        length = request.headers.get("content-length", "")
        too_large = length.isdigit() and int(length) > settings.max_upload_bytes + 1_048_576
    if too_large:
        response = JSONResponse(status_code=413, content={"detail": "Request body too large"})
    else:
        response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
        # Strict CSP for the JSON API only; Swagger UI (/docs) needs external scripts.
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    logger.info("request", extra={"ctx": {
        "request_id": request_id, "method": request.method, "path": request.url.path,
        "status": response.status_code, "duration_ms": duration_ms}})
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    # Default FastAPI output echoes the submitted input (could include a password); strip it.
    errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error("database error", exc_info=exc, extra={"ctx": {"path": request.url.path}})
    return JSONResponse(status_code=500, content={"detail": "Database error"})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error("unhandled error", exc_info=exc, extra={"ctx": {"path": request.url.path}})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(health_api.router)
app.include_router(auth_api.router)
app.include_router(audit_api.router)
app.include_router(dashboard_api.router)
app.include_router(designs_api.router)
app.include_router(quality_api.router)
app.include_router(supply_chain_api.router)
