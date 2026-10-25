import sys
from pathlib import Path
import unittest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/sgrt_zero'))
from documented_zero_links import build_documented_stars


class DocumentedLinksTests(unittest.TestCase):
    def inputs(self):
        nodes = pd.DataFrame([{'source_record_id': i, 'name': i, 'lat': 54., 'lon': 59.,
                               'population_2021': 100.} for i in ['a', 'b', 'c']])
        links = pd.DataFrame([
            {'link_id': '1', 'origin_id': 'a', 'destination_id': 'a', 'service_code': 'school_lower_secondary', 'grade_span': '1-9', 'evidence_kind': 'normative_attachment', 'source_id': 's', 'document_date': '2025-03-12'},
            {'link_id': '2', 'origin_id': 'b', 'destination_id': 'a', 'service_code': 'school_lower_secondary', 'grade_span': '1-9', 'evidence_kind': 'normative_attachment', 'source_id': 's', 'document_date': '2025-03-12'},
            {'link_id': '3', 'origin_id': 'b', 'destination_id': 'c', 'service_code': 'school_upper', 'grade_span': '10-11', 'evidence_kind': 'normative_attachment', 'source_id': 's', 'document_date': '2025-03-12'},
            {'link_id': '4', 'origin_id': 'b', 'destination_id': 'b', 'service_code': 'medical_primary_fap', 'grade_span': None, 'evidence_kind': 'provider_reported_service', 'source_id': 'm', 'document_date': None}])
        route = pd.DataFrame([{'origin_id': 'b', 'selected_provider_id': 'school-site',
                               'selected_provider_source_record_id': None,
                               'selected_provider_site_lat': 54., 'selected_provider_site_lon': 59.,
                               'cost_minutes': 3., 'provider_source_grades': None}])
        return links, nodes, {'school_general': route}

    def test_upper_grade_does_not_merge_lower_stars(self):
        stars, members, comp = build_documented_stars(*self.inputs())
        self.assertEqual(len(stars), 2)
        self.assertEqual(len(members), 3)
        self.assertNotIn('3', comp.link_id.tolist())
        self.assertEqual(set(stars.centre_id), {'a', 'b'})

    def test_zero_distance_is_not_provider_np_identity(self):
        _, _, comp = build_documented_stars(*self.inputs())
        row = comp[comp.link_id.eq('2')].iloc[0]
        self.assertEqual(row.selected_point_to_documented_centre_km, 0.)
        self.assertFalse(row.model_provider_np_identity_established)
        self.assertIsNone(row.exact_destination_np_match)
        self.assertFalse(row.grade_coverage_match_established)

    def test_exact_np_match_is_not_observed_journey_or_school_grade(self):
        links, nodes, routes = self.inputs()
        routes['school_general']['selected_provider_source_record_id'] = 'a'
        _, _, comp = build_documented_stars(links, nodes, routes)
        row = comp[comp.link_id.eq('2')].iloc[0]
        self.assertTrue(row.exact_destination_np_match)
        self.assertFalse(row.actual_journey_established)
        self.assertFalse(row.institution_identity_match_established)
        self.assertFalse(row.grade_coverage_match_established)

    def test_duplicate_or_missing_node_identity_fails(self):
        links, nodes, routes = self.inputs()
        with self.assertRaises(ValueError):
            build_documented_stars(links, pd.concat([nodes, nodes.iloc[[0]]]), routes)
        with self.assertRaises(ValueError):
            build_documented_stars(links, nodes[nodes.source_record_id.ne('a')], routes)

    def test_missing_route_remains_unknown_and_known_other_np_is_mismatch(self):
        links, nodes, routes = self.inputs()
        routes['school_general']['selected_provider_source_record_id'] = 'c'
        _, _, comp = build_documented_stars(links, nodes, routes)
        self.assertEqual(comp[comp.link_id.eq('2')].iloc[0].comparison_status, 'different_known_np')
        self.assertEqual(comp[comp.link_id.eq('1')].iloc[0].comparison_status, 'modeled_route_missing')

    def test_ambiguous_grade_is_not_lower_evidence(self):
        links, nodes, routes = self.inputs()
        links.loc[links.link_id.eq('2'), 'grade_span'] = None
        _, _, comp = build_documented_stars(links, nodes, routes)
        self.assertNotIn('2', comp.link_id.tolist())


if __name__ == '__main__':
    unittest.main()
