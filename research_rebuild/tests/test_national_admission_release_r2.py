import json
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
R1 = ROOT / "research_rebuild/evidence/releases/national_reviewed_admissions_r1_20260930"
R2 = ROOT / "research_rebuild/evidence/releases/national_reviewed_admissions_r2_20260930"


def ids(raw):
    return [] if pd.isna(raw) or not str(raw).strip() else json.loads(str(raw))


class NationalAdmissionReleaseR2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r1_manifest = json.loads((R1 / "release_manifest.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((R2 / "release_manifest.json").read_text(encoding="utf-8"))
        cls.points1 = pd.read_csv(R1 / "coordinate_admissions.csv")
        cls.points = pd.read_csv(R2 / "coordinate_admissions.csv")
        cls.edges = pd.read_csv(R2 / "identity_edges_accepted.csv")
        cls.bindings = pd.read_csv(R2 / "publication_bindings.csv")
        cls.selected = pd.read_parquet(ROOT / "research_rebuild/evidence/releases/national_source_selection_r1_20260930/selected_observations.parquet")
        cls.selected_ids = set(cls.selected.source_record_id.astype(str))

    def test_only_dependency_types_changed_from_r1(self):
        self.assertEqual(len(self.points), len(self.points1))
        shared = [c for c in self.points1.columns if c in self.points.columns]
        # These three columns are intentionally normalized; every claim, target,
        # point, year, value, decision, and evidence field stays the same.
        normalized = {"depends_on_identity_decision_ids", "published_record_binding_id"}
        for col in shared:
            if col not in normalized:
                pd.testing.assert_series_equal(self.points[col], self.points1[col], check_names=False)
        self.assertIn("depends_on_publication_binding_ids", self.points.columns)
        self.assertEqual(self.points.target_source_record_id.tolist(), self.points1.target_source_record_id.tolist())

    def test_foreign_keys_are_typed_and_resolve(self):
        identity_ids = set(self.edges.decision_id.astype(str))
        binding_ids = set(self.bindings.binding_decision_id.astype(str))
        bad_identity, bad_binding = [], []
        binding_rows = 0
        for row in self.points.itertuples(index=False):
            identity_deps = ids(row.depends_on_identity_decision_ids)
            binding_deps = ids(row.depends_on_publication_binding_ids)
            if any(x not in identity_ids for x in identity_deps):
                bad_identity.append(row.decision_id)
            if any(x not in binding_ids for x in binding_deps):
                bad_binding.append(row.decision_id)
            scalar = None if pd.isna(row.published_record_binding_id) else str(row.published_record_binding_id)
            self.assertEqual(binding_deps, [scalar] if scalar else [])
            self.assertFalse(any(x.startswith("PUBLISHED-BINDING-") for x in identity_deps))
            binding_rows += len(binding_deps)
        self.assertEqual(bad_identity, [])
        self.assertEqual(bad_binding, [])
        self.assertEqual(binding_rows, 10)

    def test_binding_revocation_is_separate_from_identity_revocation(self):
        row = self.points[self.points.depends_on_publication_binding_ids.notna() &
                          self.points.depends_on_publication_binding_ids.map(lambda x: bool(ids(x)))].iloc[0]
        binding_id = ids(row.depends_on_publication_binding_ids)[0]
        identity_deps = ids(row.depends_on_identity_decision_ids)
        # Simulate a binding revoke: only coordinate claims depending on this
        # publication assertion cascade; their identity path is still present.
        withdrawn = self.points[self.points.depends_on_publication_binding_ids.map(
            lambda x: binding_id in ids(x))]
        self.assertEqual(len(withdrawn), 1)
        self.assertTrue(set(identity_deps).issubset(set(self.edges.decision_id.astype(str))))
        self.assertTrue((self.edges.decision_id.astype(str) == identity_deps[0]).any())
        self.assertIn(row.target_source_record_id, self.selected_ids)

    def test_output_counts_coverage_and_selection_remain_unchanged(self):
        for name, entry in self.manifest["outputs"].items():
            if name != "coordinate_admissions.csv":
                self.assertEqual(entry["sha256"], self.r1_manifest["outputs"][name]["sha256"])
        self.assertEqual(self.points.groupby("target_year").size().to_dict(), {2002: 24, 2010: 24, 2021: 33})
        self.assertEqual(len(self.edges), 51)
        self.assertEqual(len(self.bindings), 10)
        coverage1 = pd.read_csv(R1 / "coverage_by_year.csv")
        coverage2 = pd.read_csv(R2 / "coverage_by_year.csv")
        pd.testing.assert_frame_equal(coverage1, coverage2)
        self.assertFalse(self.manifest["correction"]["coordinate_decisions_changed"])
        self.assertFalse(self.manifest["correction"]["identity_decisions_changed"])


if __name__ == "__main__":
    unittest.main()
