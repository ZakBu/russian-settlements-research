"""Isolated regression for proposed invocation-local point-ledger hash cache."""
from pathlib import Path
import csv
import hashlib
import tempfile
import time


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def proposed_reject_point_uses(state, path, hash_fn=digest):
    """Exact proposed loop logic, run against a lightweight state fixture."""
    ledger_hashes = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = row["target_source_record_id"]
            if row["rejection_status"] not in {
                "reviewed_rejected_coordinate_claim_only",
                "reviewed_superseded_representative_point_only",
            }:
                raise ValueError("Unsupported point rejection status")
            old = state.point_rows[sid]
            if (old["latitude"], old["longitude"]) != (float(row["old_latitude"]), float(row["old_longitude"])):
                raise ValueError("Rejected claim does not match the active point")
            ledger = row["origin_ledger"]
            if old["point_ledger_path"] != ledger:
                raise ValueError("Rejected claim ledger is not active")
            if ledger not in ledger_hashes:
                ledger_hashes[ledger] = hash_fn(Path(ledger))
            if ledger_hashes[ledger] != row["origin_ledger_sha256"]:
                raise ValueError("Rejected claim input hash differs")
            state.point_rows.pop(sid)
            state.conflicting_point_targets.discard(sid)
    state.inputs.append(Path(path))


class Fixture:
    def __init__(self, ledger):
        self.point_rows = {
            "a": {"latitude": 1.0, "longitude": 2.0, "point_ledger_path": str(ledger)},
            "b": {"latitude": 3.0, "longitude": 4.0, "point_ledger_path": str(ledger)},
        }
        self.conflicting_point_targets = {"a", "b"}
        self.inputs = []


def write_rows(path, rows):
    cols = ["target_source_record_id", "rejection_status", "old_latitude", "old_longitude", "origin_ledger", "origin_ledger_sha256"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)


def row(sid, lat, lon, ledger, expected):
    return {"target_source_record_id": sid, "rejection_status": "reviewed_superseded_representative_point_only", "old_latitude": lat, "old_longitude": lon, "origin_ledger": str(ledger), "origin_ledger_sha256": expected}


def main():
    calls = []
    def counted(path):
        calls.append(str(path)); return digest(path)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td); ledger = td / "ledger.parquet"; ledger.write_bytes(b"frozen ledger fixture")
        good = digest(ledger); p = td / "valid.csv"
        write_rows(p, [row("a", 1, 2, ledger, good), row("b", 3, 4, ledger, good)])
        st = Fixture(ledger); proposed_reject_point_uses(st, p, counted)
        assert len(calls) == 1, calls
        assert not st.point_rows and not st.conflicting_point_targets and st.inputs == [p]

        # Cached second row's wrong expected hash must still fail.
        calls.clear(); p2 = td / "bad_second.csv"
        write_rows(p2, [row("a", 1, 2, ledger, good), row("b", 3, 4, ledger, "0" * 64)])
        st = Fixture(ledger)
        try: proposed_reject_point_uses(st, p2, counted)
        except ValueError as e: assert str(e) == "Rejected claim input hash differs"
        else: raise AssertionError("cached second-row bad hash was accepted")
        assert len(calls) == 1 and "a" not in st.point_rows and "b" in st.point_rows

        # A new invocation rehashes the same path and detects changed bytes.
        calls.clear(); ledger.write_bytes(b"changed ledger fixture")
        p3 = td / "changed_between_calls.csv"; write_rows(p3, [row("a", 1, 2, ledger, good)])
        st = Fixture(ledger)
        try: proposed_reject_point_uses(st, p3, counted)
        except ValueError as e: assert str(e) == "Rejected claim input hash differs"
        else: raise AssertionError("new invocation reused a stale hash")
        assert len(calls) == 1 and "a" in st.point_rows
        ledger.write_bytes(b"frozen ledger fixture")

        # First-row hash, status, coordinate, and active-ledger checks remain enforced.
        for bad in [
            row("a", 1, 2, ledger, "0" * 64),
            {**row("a", 1, 2, ledger, good), "rejection_status": "candidate"},
            row("a", 1.5, 2, ledger, good),
            row("a", 1, 2, td / "other.parquet", good),
        ]:
            calls.clear(); px = td / "bad_first.csv"; write_rows(px, [bad]); st = Fixture(ledger)
            try: proposed_reject_point_uses(st, px, counted)
            except (ValueError, FileNotFoundError): pass
            else: raise AssertionError(f"first-row hard check bypassed: {bad}")
            assert "a" in st.point_rows, "first row mutated before its rejection checks completed"

        # Small pinned-ledger benchmark: one actual hash call and byte count.
        actual = Path('/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_point_uses.parquet')
        before = time.perf_counter(); actual_hash = digest(actual); elapsed = time.perf_counter() - before
        print({"regressions": "PASS", "valid_shared_ledger_hash_calls": 1, "bad_cached_second_hash_rejected": True, "changed_between_invocations_detected": True,
               "first_row_hash_status_coordinate_active_ledger_checks": "PASS", "actual_ledger_bytes": actual.stat().st_size,
               "actual_ledger_sha256": actual_hash, "one_hash_seconds": round(elapsed, 3),
               "one_in_memory_cache_per_invocation": True, "global_cache": False})


if __name__ == '__main__': main()
