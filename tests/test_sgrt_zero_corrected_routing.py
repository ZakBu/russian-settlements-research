"""Public-repeat identity and numerical delta checks for semantic rerouting."""
import importlib.util
from pathlib import Path
import sys

import pandas as pd
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/sgrt_zero/reroute_corrected.py'
spec = importlib.util.spec_from_file_location('reroute_corrected', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def example():
    return pd.DataFrame({'origin_id': ['a', 'b'],
                         'selected_provider_id': ['x', None],
                         'provider_settlement_id': ['c', None],
                         'cost_minutes': [5., None],
                         'unconstrained_nearest_provider_id': ['x', None],
                         'unconstrained_nearest_cost_minutes': [5., None]})


class CorrectedRoutingTests(unittest.TestCase):
    def test_order_and_nulls_do_not_create_changes(self):
        before = example()
        changes, counts = module.changed_rows(before, before.iloc[::-1])
        assert changes.empty
        assert not any(counts.values())


    def test_physical_change_is_distinct_from_np_and_small_roundoff(self):
        before = example()
        after = before.copy()
        after.loc[0, 'selected_provider_id'] = 'new'
        after.loc[0, 'cost_minutes'] += 1e-12
        changes, counts = module.changed_rows(before, after)
        assert changes.origin_id.tolist() == ['a']
        assert counts['selected_provider_id_changed'] == 1
        assert counts['provider_settlement_id_changed'] == 0
        assert counts['cost_minutes_changed'] == 0


    def test_lost_or_duplicated_origins_are_rejected(self):
        before = example()
        with self.assertRaisesRegex(ValueError, 'origin universe'):
            module.changed_rows(before, before.iloc[:1])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            module.changed_rows(before, pd.concat([before, before.iloc[:1]]))
