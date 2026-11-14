"""Public API contract v1 (docs/SPEC.md §4.1, §6).

Client-agnostic: user-facing texts are stable codes + parameters; clients localize.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["green", "yellow", "red", "unknown"]
Disposition = Literal["1+kk", "1+1", "2+kk", "2+1", "3+kk", "3+1", "4+kk", "4+1"]
ScamQuestion = Literal[
    "deposit_before_viewing",
    "video_only_viewing",
    "foreign_account",
    "owner_abroad",
    "pressure_to_pay",
    "unit_number_withheld",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- suggest ----------


class AddressSuggestion(BaseModel):
    ruian_code: int
    label: str
    lat: float
    lon: float


# ---------- report request ----------


class FeaturesIn(_Strict):
    lift: bool = False
    balcony: bool = False
    terrace: bool = False
    furnished: bool = False
    garage: bool = False
    new_build: bool = False


class ReportRequest(_Strict):
    ruian_code: int = Field(gt=0)
    unit_number: int | None = Field(default=None, ge=1, le=9999)
    rent_czk: int = Field(gt=0, le=1_000_000, description="Monthly rent WITHOUT service charges")
    area_m2: float = Field(gt=5, le=1000)
    disposition: Disposition
    landlord_ico: str | None = Field(default=None, pattern=r"^\d{8}$")
    features: FeaturesIn = FeaturesIn()
    answers: dict[ScamQuestion, bool] = {}

    @field_validator("landlord_ico", mode="before")
    @classmethod
    def _strip_ico(cls, v):
        if isinstance(v, str):
            v = v.replace(" ", "")
            return v or None
        return v


# ---------- report response ----------


class PriceBlock(BaseModel):
    status: Status
    available: bool
    verdict: Literal["far_below", "below", "typical", "above", "far_above"] | None = None
    asking_per_m2: float | None = None
    expected_per_m2: int | None = None
    # "Typical" (green) range around expected, from scoring config: clients don't hard-code it.
    typical_low_per_m2: int | None = None
    typical_high_per_m2: int | None = None
    reference_per_m2: int | None = None
    surcharge_per_m2: int | None = None
    band_low: int | None = None
    band_high: int | None = None
    raw_min: int | None = None
    raw_median: int | None = None
    raw_max: int | None = None
    coverage: int | None = None
    limited_data: bool = False
    ratio: float | None = None
    unit_name: str | None = None
    unit_kind: Literal["ku", "obec"] | None = None
    size_category: int | None = None
    period_end: dt.date | None = None


class ProceedingOut(BaseModel):
    type: str
    number: str
    state: str | None
    received: dt.datetime | None
    scope: Literal["unit", "building"]
    in_progress: bool


class PropertyBlock(BaseModel):
    status: Status
    available: bool
    unavailable_reason: Literal["quota", "service"] | None = None
    check_level: Literal["unit", "building"] | None = None
    building_found: bool | None = None
    unit_found: bool | None = None
    unit_use_code: int | None = None
    unit_use_name: str | None = None
    ku_name: str | None = None
    proceedings: list[ProceedingOut] = []
    signals: list[str] = []
    hints: list[str] = []
    kn_deeplink: str | None = None
    data_as_of: dt.datetime | None = None


class LandlordBlock(BaseModel):
    status: Status
    ico: str
    found: bool
    name: str | None = None  # never set for natural persons
    natural_person: bool | None = None
    active: bool | None = None
    insolvency: Literal["none", "active", "unknown", "not_checked"] = "not_checked"
    insolvency_stage: str | None = None
    signals: list[str] = []


class AddressBlock(BaseModel):
    status: Status
    flood_zone: Literal["none", "near", "q100", "active"] | None
    distance_m: int | None = None
    data_version: str | None = None


class ScamBlock(BaseModel):
    status: Status
    flags: list[str]


class ReportResponse(BaseModel):
    overall: Status
    price: PriceBlock
    property: PropertyBlock
    landlord: LandlordBlock | None
    address: AddressBlock
    scam_flags: ScamBlock
    disclaimer: str
    sources: list[str]
