"""Guard the map export and new-release-only publication contract."""
import subprocess
import unittest
from unittest.mock import patch
import pandas as pd

from scripts.sgrt_zero import cloud_centre_demography as cloud


class CloudDemographyTests(unittest.TestCase):
    def fixtures(self):
        centres = pd.DataFrame({'star_id': ['a', 'b'], 'centre_settlement_id': ['np-a', 'np-b'],
            'centre_name': ['А', 'Б'], 'centre_region': ['область']*2,
            'lat': [50., 51.], 'lon': [40., 41.]})
        rows = []
        for mode in ['strict_direct_observed', 'accepted_values']:
            for star, npid in [('a', 'np-a'), ('b', 'np-b')]:
                rows.append({'star_id': star, 'centre_settlement_id': npid, 'evidence_mode': mode,
                    'joint_centre_rural_external_2002_2021': 'unknown' if mode.startswith('strict') and star == 'a' else 'growth__growth',
                    'joint_centre_rural_external_2010_2021': 'unknown' if mode.startswith('strict') else 'decline__growth'})
        return pd.DataFrame(rows), centres

    def test_map_has_one_row_per_centre_and_main_class_never_uses_accepted_values(self):
        classes, centres = self.fixtures()
        result = cloud.site_frame(classes, centres).set_index('star_id')
        self.assertEqual(len(result), 2)
        self.assertEqual(result.loc['a', 'demography_rural_2002_category'], 0)
        self.assertEqual(result.loc['b', 'demography_rural_2002_category'], 2)
        self.assertEqual(result.loc['a', 'accepted_joint_centre_rural_external_2010_2021'], 'decline__growth')
        self.assertFalse(result.word_causal_type_established.any())
        self.assertFalse(result.historical_boundary_equivalence_established.any())
        self.assertEqual(result.loc['a', 'lat'], 50.)

    def test_missing_duplicate_modes_or_unrecognised_classes_fail(self):
        classes, centres = self.fixtures()
        for changed in [classes.iloc[1:], pd.concat([classes, classes.iloc[:1]])]:
            with self.assertRaises(ValueError): cloud.site_frame(changed, centres)
        classes.loc[0, 'joint_centre_rural_external_2002_2021'] = 'causal_word_type'
        with self.assertRaisesRegex(ValueError, 'Unexpected'): cloud.site_frame(classes, centres)

    def test_only_explicit_404_for_both_release_and_git_tag_is_safe(self):
        missing = subprocess.CompletedProcess([], 1, '', 'gh: Not Found (HTTP 404)')
        exists = subprocess.CompletedProcess([], 0, '{}', '')
        denied = subprocess.CompletedProcess([], 1, '', 'gh: Forbidden (HTTP 403)')
        with patch.object(cloud.subprocess, 'run', side_effect=[missing, missing]): cloud.absent_tag()
        for responses in [[exists], [missing, exists]]:
            with patch.object(cloud.subprocess, 'run', side_effect=responses):
                with self.assertRaisesRegex(ValueError, 'new tag'): cloud.absent_tag()
        with patch.object(cloud.subprocess, 'run', return_value=denied):
            with self.assertRaises(RuntimeError): cloud.absent_tag()


if __name__ == '__main__': unittest.main()
