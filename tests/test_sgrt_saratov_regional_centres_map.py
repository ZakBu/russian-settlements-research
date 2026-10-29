import json
import unittest
import pandas as pd

from scripts.sgrt_saratov.regional_centres_map import build


def profile(identity, count=1, regional=True, scenario='all_dated_known'):
    return dict(centre_id=identity, centre_name=identity, evidence_scenario=scenario,
                centre_in_regional_roster=regional, known_own_basic_function_count=count,
                known_own_basic_functions_json=json.dumps(['school', 'medical_basic', 'grocery'][:count]),
                centre_population_2021=100., external_positive_origin_count=2,
                external_rural_positive_origin_count=1, external_credited_rural_population_2021=9.,
                external_rural_population_summary_complete=False, inventory_scenario='test')


class RegionalCentreLocations(unittest.TestCase):
    def roster(self):
        return pd.DataFrame([dict(source_record_id='a', lon=47., lat=51., accepted_point_present=True),
                             dict(source_record_id='b', lon=float('nan'), lat=float('nan'), accepted_point_present=False)])

    def test_external_and_other_scenario_profiles_do_not_inflate_count(self):
        p = pd.DataFrame([profile('a', 3), profile('foreign', regional=False),
                          profile('a', 1, scenario='nonhistorical_only')])
        geo, summary = build(p, self.roster())
        self.assertEqual(summary['regional_profile_count'], 1)
        self.assertEqual(geo['features'][0]['geometry']['coordinates'], [47., 51.])
        self.assertEqual(geo['features'][0]['properties']['class_index'], 2)
        self.assertFalse(geo['features'][0]['properties']['external_rural_population_summary_complete'])
        self.assertFalse(summary['catchment_boundaries_inferred'])

    def test_unknown_coordinate_is_held_not_guessed_or_zero(self):
        geo, summary = build(pd.DataFrame([profile('a'), profile('b')]), self.roster())
        self.assertEqual(len(geo['features']), 1)
        self.assertEqual(summary['held_centre_count'], 1)
        self.assertEqual(summary['known_own_basic_function_counts']['1'], 2)

    def test_inconsistent_function_count_is_rejected(self):
        p = pd.DataFrame([profile('a')]); p.loc[0, 'known_own_basic_function_count'] = 3
        with self.assertRaises(ValueError): build(p, self.roster())


if __name__ == '__main__': unittest.main()
