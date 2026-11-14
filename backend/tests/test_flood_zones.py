import zipfile

import numpy as np
import pyogrio.raw
import pytest
import shapely

from app.ingest.flood_zones import FloodFormatError, load
from app.services.flood import check_point

# Around U křížku 1403/4 (S-JTSK x=-741290, y=-1046043).
X, Y = -741290.0, -1046043.0


def square(cx, cy, half):
    return shapely.box(cx - half, cy - half, cx + half, cy + half)


def shp_zip(tmp_path, name, polygons, crs="EPSG:5514"):
    shp = tmp_path / f"{name}.shp"
    pyogrio.raw.write(
        shp,
        geometry=np.array([shapely.to_wkb(p) for p in polygons], dtype=object),
        field_data=[np.array(["Botič"] * len(polygons), dtype=object)],
        fields=["NAZ_TOK"],
        crs=crs,
        driver="ESRI Shapefile",
        geometry_type="Polygon",
    )
    z = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in tmp_path.glob(f"{name}.*"):
            if f.suffix != ".zip":
                zf.write(f, f.name)
    return z


@pytest.fixture
def archives(tmp_path):
    q100 = shp_zip(tmp_path, "q100", [square(X, Y, 50), square(X + 1000, Y, 50)])
    active = shp_zip(tmp_path, "az", [square(X + 1000, Y, 20)])
    return {"q100": q100, "active": active}


def test_load_and_classify(db, archives):
    assert load(db, archives, "test") > 0
    assert check_point(db, X, Y, 100).zone == "q100"
    assert check_point(db, X + 1000, Y, 100).zone == "active"
    near = check_point(db, X + 120, Y, 100)  # 70 m east of the q100 square edge
    assert (near.zone, near.distance_m) == ("near", 70)
    assert check_point(db, X + 5000, Y, 100).zone == "none"
    assert load(db, archives, "test") is None  # idempotent


def test_no_data_is_unknown(db):
    assert check_point(db, X, Y, 100).zone is None


def test_rejects_wrong_crs(db, tmp_path):
    bad = shp_zip(tmp_path, "wgs", [shapely.box(14, 50, 14.1, 50.1)], crs="EPSG:4326")
    with pytest.raises(FloodFormatError, match="5514"):
        load(db, {"q100": bad, "active": bad}, "x")
