from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.api.deps import Services, get_services
from app.api.protection import client_ip, hashed
from app.api.v1.schemas import ReportRequest, ReportResponse
from app.services.report import ReportDeps, build_report

router = APIRouter()
DAY = 86400


@router.post("/report", response_model=ReportResponse)
def report(
    req: ReportRequest,
    request: Request,
    svc: Annotated[Services, Depends(get_services)],
    accept_language: Annotated[str | None, Header()] = None,
):
    """Computed on request, never stored."""
    settings = svc.settings
    p = settings.protection
    salt = settings.rate_limit_salt.get_secret_value()

    identity = svc.attestation.verify(request)
    ip = hashed("ip", client_ip(request, settings), salt)
    svc.limiter.hit(f"{ip}:report", p.report_per_ip_per_hour, 3600)
    if identity.device_key:
        svc.limiter.hit(
            f"{hashed('dev', identity.device_key, salt)}:report", p.report_per_device_per_day, DAY
        )

    budget_key = "global:api_kn"
    deps = ReportDeps(
        engine=svc.engine,
        api_kn=svc.api_kn(),
        ares=svc.ares(),
        isir=svc.isir(),
        scoring=settings.scoring,
        api_kn_budget_ok=lambda: svc.limiter.current(budget_key, DAY) < p.api_kn_daily_budget,
        on_api_kn_calls=lambda n: n and svc.limiter.add(budget_key, DAY, n),
    )
    lang = "en" if (accept_language or "").lower().startswith("en") else "cs"
    return build_report(req, deps, lang)
