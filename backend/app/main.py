import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import Services, make_services
from app.api.protection import make_attestation
from app.api.v1 import address, health, report
from app.config import Settings, get_settings
from app.db import get_engine

log = logging.getLogger("app.access")


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
        # httpx logs full URLs (address codes, IČO) → keep it quiet (SPEC §4).
        logging.getLogger("httpx").setLevel(logging.WARNING)
        svc = services or make_services(settings, get_engine(), make_attestation(settings))
        app.state.services = svc
        svc.limiter.cleanup()
        yield
        if services is None:
            svc.http_kn.close()
            svc.http_registers.close()

    app = FastAPI(title="Férový nájem API", version="0.2.0", lifespan=lifespan)
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        # No query string, no client IP: queries contain addresses (SPEC §4).
        start = time.perf_counter()
        response = await call_next(request)
        log.info(
            "%s %s %s %.0fms",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - start) * 1000,
        )
        return response

    app.include_router(health.router, prefix="/v1", tags=["meta"])
    app.include_router(address.router, prefix="/v1", tags=["address"])
    app.include_router(report.router, prefix="/v1", tags=["report"])
    return app


app = create_app()
