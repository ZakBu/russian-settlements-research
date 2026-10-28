"""Small contract checks; no download, graph load, complete run or publication."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from scripts.sgrt_field_pilot import cloud_pilot as cloud
from scripts.research_data import archive_member


class CloudSourceContract(unittest.TestCase):
    def test_all_ten_public_source_members_are_exact_and_extractable(self):
        total = 0
        for catalog, paths in cloud.INPUTS.items():
            cat = json.loads((cloud.REPO / catalog).read_text())
            for path in paths:
                matches = [r for r in cat["files"] if r["path"] == path]
                self.assertEqual(len(matches), 1, path)
                row = matches[0]
                obj = cat["objects"][row["blob"]]
                self.assertRegex(obj["sha256"], r"^[a-f0-9]{64}$")
                self.assertEqual(row["bytes"], obj["bytes"])
                self.assertGreater(row["bytes"], 0)
                self.assertTrue(archive_member(obj, row["blob"]))
                self.assertIn(row["asset"], {a["asset"] for a in cat["assets"]})
                total += 1
        self.assertEqual(total, 10)


class TinyExportAndControl(unittest.TestCase):
    def test_export_distinguishes_both_gain_loss_neither_and_unknown_peaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("inputs", "model", "functions"):
                (root / name).mkdir()
            ids = list("abcde")
            pd.DataFrame({"source_record_id": ids, "name": ids,
                "lat": [50.] * 5, "lon": [40.] * 5, "pilot": ["p"] * 5,
                "evaluation_core": [True] * 5, "population_2021": [10., 0., 20., 5., 1.]}).to_csv(
                    root / "inputs/evaluation.csv", index=False)
            fields, peaks = [], []
            for half, flags in [(20, [False, True, True, False, None]),
                                (80, [False, True, False, True, None])]:
                for identity, flag in zip(ids, flags):
                    fields.append({"source_record_id": identity, "kernel": "exponential",
                        "include_self": True, "half_time_minutes": half,
                        "known_routed_potential": 100., "known_mass_potential_upper": 200.})
                    peaks.append({"source_record_id": identity, "kernel": "exponential",
                        "include_self": True, "half_time_minutes": half, "neighbor_count": 6,
                        "is_sampled_local_maximum": flag})
            pd.DataFrame(fields).to_parquet(root / "model/fields.parquet", index=False)
            pd.DataFrame(peaks).to_parquet(root / "model/peaks.parquet", index=False)
            pd.DataFrame({"source_record_id": ids, "known_local_basic_function_count": [0, 1, 2, 3, 0],
                "published_external_serving_centre": [False, True, True, True, False]}).to_parquet(
                    root / "functions/settlement_function_comparison.parquet", index=False)
            exported = cloud.site_export(root)
            self.assertEqual(exported.id.tolist(), ids)
            self.assertEqual(exported.peak_change_20_80.tolist(), [0, 1, 2, 3, 4])
            self.assertEqual(exported.loc[1, "population2021"], 0)
            self.assertFalse(exported.complete_field_or_hierarchy_established.any())

    def test_control_detects_omitted_rows_and_zero_substitution_for_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("inputs", "model", "functions"):
                (root / name).mkdir()
            for folder in ("inputs", "functions"):
                pd.DataFrame({"id": ["a"], "value": [1]}).to_csv(root / folder / "tiny.csv", index=False)
            pd.DataFrame({"id": ["a"], "value": [1]}).to_csv(root / "field-pilot-points.csv", index=False)
            frame = pd.DataFrame({"id": ["a", "b"], "value": [None, 1.]})
            path = root / "model/tiny.parquet"
            frame.to_parquet(path, index=False)
            baseline = cloud.control(root)
            frame.fillna({"value": 0}).to_parquet(path, index=False)
            self.assertNotEqual(baseline, cloud.control(root))
            frame.iloc[:1].to_parquet(path, index=False)
            self.assertNotEqual(baseline, cloud.control(root))
            frame.to_parquet(path, index=False)
            self.assertEqual(baseline, cloud.control(root))


class DraftGuards(unittest.TestCase):
    def built(self, directory):
        root = Path(directory)
        data = root / "field-pilot.zip"
        data.write_bytes(b"tiny-test-only")
        (root / "release_notes.md").write_text("test")
        manifest = {"source_commit": "producer", "release_tag": cloud.TAG,
            "archive": {"asset": data.name, "bytes": data.stat().st_size,
                        "sha256": hashlib.sha256(data.read_bytes()).hexdigest()},
            "standalone_assets": {}}
        (root / "manifest.json").write_text(json.dumps(manifest))
        return root

    def test_existing_release_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            built = self.built(tmp)
            with patch.object(cloud, "clean_commit"), \
                    patch.object(cloud, "releases", return_value=[{"tag_name": cloud.TAG}]), \
                    patch.object(cloud.subprocess, "run") as command:
                with self.assertRaisesRegex(ValueError, "immutable"):
                    cloud.draft(built, "producer")
                command.assert_not_called()

    def test_ambiguous_tag_error_does_not_create_a_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            built = self.built(tmp)
            denied = subprocess.CompletedProcess([], 1, "", "HTTP 401 Unauthorized")
            with patch.object(cloud, "clean_commit"), \
                    patch.object(cloud, "releases", return_value=[]), \
                    patch.object(cloud.subprocess, "run", return_value=denied) as command:
                with self.assertRaisesRegex(ValueError, "absence of tag"):
                    cloud.draft(built, "producer")
                self.assertEqual(command.call_count, 1)

    def test_proven_absent_tag_only_creates_a_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            built = self.built(tmp)
            absent = subprocess.CompletedProcess([], 1, "", "HTTP 404 Not Found")
            created = subprocess.CompletedProcess([], 0, "", "")
            with patch.object(cloud, "clean_commit"), \
                    patch.object(cloud, "releases", return_value=[]), \
                    patch.object(cloud.subprocess, "run", side_effect=[absent, created]) as command:
                cloud.draft(built, "producer")
                create = command.call_args_list[1].args[0]
                self.assertEqual(create[:3], ["gh", "release", "create"])
                self.assertIn("--draft", create)
                self.assertNotIn("--clobber", create)


if __name__ == "__main__":
    unittest.main()
