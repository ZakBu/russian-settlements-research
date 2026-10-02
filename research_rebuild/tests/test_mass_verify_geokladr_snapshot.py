import tempfile
import unittest
from pathlib import Path

from research_rebuild.mass_linkage.verify_geokladr_snapshot import parse_dbf_records, _equal_raw_to_legacy


FIELDS = [
    ("TER", "C", 2, 0), ("KOD1", "C", 3, 0), ("KOD2", "C", 3, 0), ("KOD3", "C", 3, 0),
    ("NAME1", "C", 160, 0), ("SCOKATO", "C", 25, 0), ("KLADRCODE", "C", 13, 0),
    ("DATA_UPD", "C", 10, 0), ("OKTMO", "C", 8, 0), ("LONG", "N", 16, 6),
    ("LAT", "N", 16, 6), ("STATUS", "N", 20, 5), ("POPULATION", "N", 13, 0),
]


def make_dbf(path: Path) -> None:
    header_length = 32 + 32 * len(FIELDS) + 1
    record_length = 1 + sum(field[2] for field in FIELDS)
    header = bytearray(32)
    header[0] = 3
    header[4:8] = (2).to_bytes(4, "little")
    header[8:10] = header_length.to_bytes(2, "little")
    header[10:12] = record_length.to_bytes(2, "little")
    descriptors = bytearray()
    for name, kind, width, decimals in FIELDS:
        d = bytearray(32)
        d[:len(name)] = name.encode("ascii")
        d[11] = ord(kind)
        d[16] = width
        d[17] = decimals
        descriptors.extend(d)

    def record(marker: bytes, values: dict[str, bytes]) -> bytes:
        out = bytearray(marker)
        for name, _kind, width, _decimals in FIELDS:
            raw = values.get(name, b" ")
            out.extend(raw[:width].ljust(width, b" "))
        return bytes(out)

    vals = {
        "TER": b"01", "KOD1": b"018", "KOD2": b"020", "KOD3": b"001",
        "NAME1": "п Алейский".encode("cp1251"), "SCOKATO": "п".encode("cp1251"),
        "KLADRCODE": b"2200200000500", "DATA_UPD": b"2011/06/20", "OKTMO": b"        ",
        "LONG": b"       82.728172", "LAT": b"       52.470009", "STATUS": b"             0.00000",
        "POPULATION": b"            0",
    }
    blank = dict(vals)
    blank.update({"OKTMO": b"        ", "LONG": b"                ", "LAT": b"                "})
    path.write_bytes(bytes(header) + bytes(descriptors) + b"\x0d" + record(b" ", vals) + record(b"*", blank))


class GeoKladrRawVerificationTests(unittest.TestCase):
    def test_raw_dbf_preserves_leading_zero_cp1251_blank_numeric_and_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "okato.dbf"
            make_dbf(path)
            meta, rows = parse_dbf_records(path)
        self.assertEqual(meta["record_count"], 2)
        self.assertEqual(rows[0]["historical_okato"], "01018020001")
        self.assertEqual(rows[0]["name_raw"], "п Алейский")
        self.assertEqual(rows[0]["settlement_type_raw"], "п")
        self.assertEqual(rows[0]["kladr"], "2200200000500")
        self.assertEqual(rows[0]["source_updated_at"], "2011/06/20")
        self.assertEqual(rows[0]["longitude_from_long"], 82.728172)
        self.assertEqual(rows[0]["latitude_from_lat"], 52.470009)
        self.assertIsNone(rows[0]["oktmo_2011_raw"])
        self.assertTrue(rows[1]["is_deleted"])
        self.assertEqual(rows[1]["deleted_marker_raw"], "*")
        self.assertIsNone(rows[1]["longitude_from_long"])
        self.assertIsNone(rows[1]["latitude_from_lat"])
        self.assertEqual(rows[1]["source_updated_at"], "2011/06/20")

    def test_null_empty_is_not_zero_and_coordinates_are_numeric(self):
        self.assertTrue(_equal_raw_to_legacy(None, None))
        self.assertFalse(_equal_raw_to_legacy(None, 0))
        self.assertTrue(_equal_raw_to_legacy(82.728172, 82.728172))
        self.assertFalse(_equal_raw_to_legacy(82.728172, 52.470009))


if __name__ == "__main__":
    unittest.main()
