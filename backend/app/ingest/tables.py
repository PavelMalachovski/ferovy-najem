"""SQLAlchemy Core table definitions (schema is owned by Alembic migrations)."""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    Text,
)

metadata = MetaData()

rent_map_dataset = Table(
    "rent_map_dataset",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("period_end", Date, nullable=False),
    Column("source_url", Text),
    Column("sha256", Text, nullable=False),
)

rent_map_value = Table(
    "rent_map_value",
    metadata,
    Column("dataset_id", Integer, primary_key=True),
    Column("unit_code", Integer, primary_key=True),
    Column("unit_kind", Text, nullable=False),
    Column("kraj", Text, nullable=False),
    Column("unit_name", Text, nullable=False),
    Column("obec_name", Text, nullable=False),
    Column("size_category", SmallInteger, primary_key=True),
    *(
        Column(n, Integer, nullable=False)
        for n in (
            "reference",
            "band_low",
            "band_high",
            "reference_new_build",
            "raw_min",
            "raw_max",
            "raw_median",
        )
    ),
    Column("coverage", SmallInteger, nullable=False),
)

rent_map_surcharge = Table(
    "rent_map_surcharge",
    metadata,
    Column("dataset_id", Integer, primary_key=True),
    Column("new_build", Boolean, primary_key=True),
    Column("size_category", SmallInteger, primary_key=True),
    *(
        Column(n, Integer, nullable=False)
        for n in ("balcony", "terrace", "furnished", "garage", "lift")
    ),
)
