import base64
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.api.deps import Services, get_services
from app.api.protection import client_ip, hashed

router = APIRouter()


class ChallengeOut(BaseModel):
    required: bool
    challenge: str | None  # base64; null when attestation is disabled


class RegisterIn(BaseModel):
    key_id: str  # base64, from DCAppAttestService.generateKey
    attestation: str  # base64 attestation object
    challenge: str  # base64, as received from /attest/challenge


def _limit(request: Request, svc: Services) -> None:
    s = svc.settings
    ip = hashed("ip", client_ip(request, s), s.rate_limit_salt.get_secret_value())
    svc.limiter.hit(f"{ip}:attest", s.protection.attest_per_ip_per_hour, 3600)


@router.post("/attest/challenge", response_model=ChallengeOut)
def challenge(request: Request, svc: Annotated[Services, Depends(get_services)]):
    _limit(request, svc)
    c = svc.attestation.new_challenge()
    return ChallengeOut(
        required=svc.attestation.required, challenge=base64.b64encode(c).decode() if c else None
    )


@router.post("/attest/register", status_code=204)
async def register(
    body: RegisterIn, request: Request, svc: Annotated[Services, Depends(get_services)]
):
    try:
        key_id = base64.b64decode(body.key_id, validate=True)
        attestation = base64.b64decode(body.attestation, validate=True)
        challenge = base64.b64decode(body.challenge, validate=True)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"code": "invalid_base64"}) from e
    await run_in_threadpool(_limit, request, svc)
    await run_in_threadpool(svc.attestation.register, key_id, attestation, challenge)
    return Response(status_code=204)
