"""Old exploratory output must not contaminate a clean regional control."""
from pathlib import Path
import tempfile
import unittest

from scripts.sgrt_saratov.cloud_regional_research import scientific_files


class ProducerInventory(unittest.TestCase):
    def test_eight_origin_probe_is_separate_but_current_sensitivity_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            current = {
                'fields/fields.parquet',
                'field_sensitivity/mass_scope_summary.json',
                'field_sensitivity/selected_unbounded_full_costs.npz',
                'field_sensitivity/ordinary_horizon480_reference/summary.json',
            }
            historical = {
                'field_sensitivity/unbounded_federal_city_costs.parquet',
                'field_sensitivity/unbounded_selected_origins.parquet',
                'field_sensitivity/summary.json',
            }
            for name in current | historical:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            selected = {p.relative_to(root).as_posix() for p in scientific_files(root)}
            self.assertEqual(selected, current)


if __name__ == '__main__':
    unittest.main()
