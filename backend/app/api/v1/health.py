from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.db import check_db

router = APIRouter()


class Health(BaseModel):
    status: str
    db: str


def get_db_check() -> Callable[[], bool]:
    return check_db


@router.get("/health", response_model=Health)
def health(response: Response, db_check: Annotated[Callable[[], bool], Depends(get_db_check)]):
    db_ok = db_check()
    if not db_ok:
        response.status_code = 503
    return Health(status="ok" if db_ok else "degraded", db="ok" if db_ok else "unavailable")
