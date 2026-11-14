"""Builds a small synthetic MF rent-map XLSX with the real layout (SPEC §5.2).
Values are fake: the MF file has no licence statement, so it is not committed."""

from pathlib import Path

import openpyxl

BLOCK_HEADER = [
    "VK",
    "Nájemné referenčního bytu za m² v Kč za 1 měsíc",
    "Dolní interval nájemného u referenčního bytu za m² v Kč za 1 měsíc",
    "Horní interval nájemného u referenčního bytu za m² v Kč za 1 měsíc",
    "Nájemné referenčního bytu novostavby za m² v Kč za 1 měsíc",
    "Minimální hodnota nájemného za m² v Kč",
    "Maximální hodnota nájemného za m² v Kč",
    "Mediánová hodnota nájemného za m² v Kč",
    "Datová pokrytost",
]
SURCHARGE_TITLE = (
    "Přehled cen cenotvorných parametrů (dodatečných vlastností bytu) pro referenční byt"
)
SURCHARGE_HEADER = [
    "Velikostní kategorie",
    'Cena v Kč za atribut "balkón"',
    'Cena v Kč za atribut "terasa"',
    'Cena v Kč za atribut "vybavennost"',
    'Cena v Kč za atribut "garáž"',
    'Cena v Kč za atribut "výtah"',
]

# (kraj, k.ú. name or None, obec, code, base reference)
ROWS = [
    ("Hlavní město Praha", "Nusle", "Praha", 728161, 450),
    ("Hlavní město Praha", "Vinohrady", "Praha", 727164, 470),
    ("Jihočeský kraj", None, "Kalenice", 536946, 190),
]


def block(vk: int, ref: int) -> list:
    r = ref - 10 * (vk - 1)
    return [vk, r, r - 10, r + 10, r + 150, r - 300, r + 500, r - 5, 5 if ref > 400 else 1]


def build(path: Path, *, period_text: str | None = None, rows=ROWS, broken_band=False) -> Path:
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "Základní informace"

    class _Offset:
        """The real info sheet starts in column C."""

        def append(self, row):
            sheet.append([None, None, *row] if row else [])

    info = _Offset()
    info.append(["Cenová mapa nájemného poskytuje přehled výše nájmů…"])
    info.append(
        [period_text or "Výpočet cenových map vychází z dat z období od 1.10.2021 do 30.9.2026."]
    )
    info.append([])
    info.append([SURCHARGE_TITLE + "  v Kč/m²"])
    info.append(SURCHARGE_HEADER)
    for vk, vals in enumerate(
        [[16, 36, 30, 45, 41], [8, 38, 32, 49, 45], [4, 34, 27, 38, 48], [8, 26, 23, 33, 61]], 1
    ):
        info.append([f"VK{vk}", *vals])
    info.append([])
    info.append([SURCHARGE_TITLE + " novostavba  v Kč/m²"])
    info.append([*SURCHARGE_HEADER, 'Cena v Kč za atribut "jiný typ konstrukčního materiálu"'])
    for vk, vals in enumerate(
        [[15, 28, 26, 36, 19], [11, 26, 29, 43, 16], [9, 26, 23, 45, 17], [7, 24, 19, 43, 19]], 1
    ):
        info.append([f"VK{vk}", *vals, 40])

    data = wb.create_sheet("Cenové mapy nájemného")
    header = ["Kraj", "Katastrální území", "Obec", "Kód obce"]
    for i in range(4):
        header += BLOCK_HEADER + ([None] if i < 3 else [])
    data.append(header)
    for kraj, ku, obec, code, ref in rows:
        line = [kraj, ku, obec, code]
        for vk in range(1, 5):
            b = block(vk, ref)
            if broken_band and vk == 1:
                b[1] = b[3] + 1  # reference above upper band
            line += b + ([None] if vk < 4 else [])
        data.append(line)
    wb.save(path)
    return path
