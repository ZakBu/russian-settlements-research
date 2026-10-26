"""Scope controls for frozen OSM primary-care proxies, without brand bans."""
from pathlib import Path
import json
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.sgrt_zero.medical_need_review import review_medical_need_scope


class MedicalNeedReviewTests(unittest.TestCase):
    def frame(self, tags, **extra):
        row = dict(provider_id='osm-med:OSM:way:108548965:medical_basic_primary',
                   provider_name='Республиканская психотерапевтическая поликлиника',
                   service_code='medical_basic_primary', supply_status='proxy',
                   eligible=True, route_eligible=True, site_lat=42.9, site_lon=47.5,
                   function_assignment_verified_by_licence=False,
                   source_tags_json=json.dumps(tags, ensure_ascii=False))
        row.update(extra)
        return pd.DataFrame([row], index=[7])

    def test_frozen_polyclinic_label_does_not_override_sole_psychiatry(self):
        for service in ['medical_basic_primary', 'medical_physician_primary']:
            frame = self.frame({'healthcare': 'clinic', 'healthcare:speciality': 'psychiatry'},
                               service_code=service)
            result = review_medical_need_scope(frame)
            self.assertFalse(result.route_eligible.iloc[0])
            self.assertEqual(result.need_scope_review_reason.iloc[0],
                             'sole_psychiatry_specialty_not_evidence_of_general_primary_need')
            pd.testing.assert_frame_equal(frame.drop(columns='route_eligible'),
                                          result[frame.columns].drop(columns='route_eligible'))

    def test_mixed_general_practice_is_not_a_psychiatry_only_contradiction(self):
        for specialty in ['general', 'general_practice', 'general_medicine',
                          'family_medicine', 'family_practice', 'internal']:
            result = review_medical_need_scope(self.frame(
                {'healthcare:speciality': 'psychiatry;' + specialty}))
            self.assertTrue(result.route_eligible.iloc[0])
            self.assertEqual(result.need_scope_review_reason.iloc[0], '')

    def test_explicit_therapist_token_is_distinct_from_psychotherapist(self):
        for person_type, expected in [('physician;therapist', True), ('psychotherapist', False)]:
            result = review_medical_need_scope(self.frame(
                {'healthcare:speciality': 'psychiatry', 'health_person:type': person_type}))
            self.assertEqual(bool(result.route_eligible.iloc[0]), expected)

    def test_same_unit_verified_primary_function_can_override_osm_specialty(self):
        result = review_medical_need_scope(self.frame(
            {'healthcare:speciality': 'psychiatry'}, function_assignment_verified_by_licence=True))
        self.assertTrue(result.route_eligible.iloc[0])
        # A generic organisation licence identifier does not establish the
        # function of the physical unit represented by this mapped feature.
        result = review_medical_need_scope(self.frame(
            {'healthcare:speciality': 'psychiatry', 'operator:licence': 'organisation-licence'}))
        self.assertFalse(result.route_eligible.iloc[0])

    def test_helix_branch_general_and_therapist_are_not_excluded_by_brand(self):
        tags = {'healthcare': 'laboratory', 'healthcare:speciality': 'general',
                'health_person:type': 'physician;therapist;physician_assitant',
                'name': 'Хеликс', 'website': 'https://helix.ru/center/19973'}
        result = review_medical_need_scope(self.frame(tags, provider_name='Хеликс'))
        self.assertTrue(result.route_eligible.iloc[0])
        for name in ['Хеликс', 'МЕДСИ', 'Гемотест']:
            result = review_medical_need_scope(self.frame({}, provider_name=name))
            self.assertTrue(result.route_eligible.iloc[0])

    def test_existing_hold_and_raw_values_survive_without_a_new_scope_claim(self):
        frame = self.frame({}, provider_name='Медицинский центр', route_eligible=False)
        result = review_medical_need_scope(frame)
        self.assertFalse(result.route_eligible.iloc[0])
        pd.testing.assert_frame_equal(frame, result[frame.columns])
        self.assertEqual(result.need_scope_review_reason.iloc[0], '')

    def test_absent_malformed_or_nonobject_tags_remain_unknown(self):
        for raw in [None, '{broken', '[]']:
            frame = self.frame({}, provider_name='Поликлиника')
            frame['source_tags_json'] = raw
            result = review_medical_need_scope(frame)
            self.assertTrue(result.route_eligible.iloc[0])
        frame = self.frame({'healthcare:speciality': 'psychiatry'}, service_code='unspecified_healthcare')
        result = review_medical_need_scope(frame)
        self.assertTrue(result.route_eligible.iloc[0])


if __name__ == '__main__':
    unittest.main()
