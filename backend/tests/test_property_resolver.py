import copy

from app.services.property import encoded_unit_numbers, resolve
from tests.api_kn_fake import FakeApiKn, load

BUILDING = "/Stavby/AdresniMisto/21951977"


def building_with(**changes) -> dict:
    body = copy.deepcopy(load("stavba_adresni_misto_21951977.json"))
    body["data"].update(changes)
    return body


def test_encoded_unit_numbers():
    assert encoded_unit_numbers([1403], 24) == {14030024}
    assert encoded_unit_numbers([1403, 1404], 2) == {14030002, 14040002}


def test_unit_found_is_flat_no_proceedings():
    fake = FakeApiKn()
    p = resolve(fake.client(), 21951977, unit_number=24)
    assert p.building.ku_code == 728161
    assert p.building.obec_code == 554782
    assert p.check_level == "unit"
    assert p.unit_found is True
    assert p.unit.use_code == 1  # byt
    assert p.unit.cislo_jednotky == 14030024
    assert p.proceedings == []
    assert p.hints == []
    assert fake.requests == [BUILDING, "/Jednotky/24136425010"]  # no /Parcely call


def test_unknown_unit_number():
    fake = FakeApiKn()
    p = resolve(fake.client(), 21951977, unit_number=99)
    assert p.check_level == "unit"
    assert p.unit_found is False
    assert fake.requests == [BUILDING]


def test_no_unit_number_is_building_level_with_hint():
    p = resolve(FakeApiKn().client(), 21951977)
    assert p.check_level == "building"
    assert p.unit_found is None
    assert p.hints == ["ask_unit_number"]


def test_whole_house_without_units():
    fake = FakeApiKn({BUILDING: (200, building_with(jednotky=[]))})
    p = resolve(fake.client(), 21951977, unit_number=24)
    assert p.hints == ["whole_house"]
    assert p.check_level == "building"


def test_building_proceedings_in_progress_and_finished():
    plomby = [
        {
            "id": 110041154010,
            "typRizeni": "V",
            "poradoveCislo": 75142,
            "rok": 2026,
            "kodPracoviste": 101,
        },
        {
            "id": 110039944010,
            "typRizeni": "Z",
            "poradoveCislo": 49575,
            "rok": 2026,
            "kodPracoviste": 101,
        },
    ]
    fake = FakeApiKn({BUILDING: (200, building_with(rizeniPlomby=plomby))})
    p = resolve(fake.client(), 21951977)
    by_type = {r.type: r for r in p.proceedings}
    assert by_type["V"].in_progress is True
    assert by_type["V"].number == "V-75142/2026-101"
    assert by_type["V"].scope == "building"
    assert by_type["Z"].in_progress is False  # "Řízení bylo ukončeno"


def test_address_not_found():
    p = resolve(FakeApiKn().client(), 1)
    assert p.building is None
