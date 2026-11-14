from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from app.api.deps import Services, get_services
from app.api.protection import client_ip, hashed
from app.api.v1.schemas import AddressSuggestion

router = APIRouter()

# word_similarity (<%) suits type-ahead: the query is a fragment of the label.
_SQL = text(
    """
    SELECT ruian_code, label, ST_Y(geom) AS lat, ST_X(geom) AS lon
    FROM address_point
    WHERE :q <% search_text
    ORDER BY (search_text LIKE :prefix) DESC, word_similarity(:q, search_text) DESC, label
    LIMIT :limit
    """
)


@router.get("/address/suggest", response_model=list[AddressSuggestion])
def suggest(
    request: Request,
    svc: Annotated[Services, Depends(get_services)],
    q: Annotated[str, Query(min_length=3, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
):
    p = svc.settings.protection
    ip = hashed(
        "ip", client_ip(request, svc.settings), svc.settings.rate_limit_salt.get_secret_value()
    )
    svc.limiter.hit(f"{ip}:suggest", p.suggest_per_ip_per_minute, 60)

    with svc.engine.connect() as c:
        norm = c.execute(text("SELECT lower(f_unaccent(:q))"), {"q": q.strip()}).scalar()
        rows = c.execute(_SQL, {"q": norm, "prefix": norm + "%", "limit": limit}).mappings()
        return [AddressSuggestion(**r) for r in rows]
