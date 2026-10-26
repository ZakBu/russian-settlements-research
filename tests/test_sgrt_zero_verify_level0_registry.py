import json
import math
import unittest
from pathlib import Path
import tempfile
import hashlib

import numpy as np
import pandas as pd

from scripts.sgrt_zero.verify_level0_registry import verify_frames, sphere_diameter, validate_hold_records, load_hold_manifest


def fixture():
    """A hand-specified overlapping registry, including an uncredited actor."""
    rows = []
    for uid, name, population, credit, role, longitude, active in [
        ('c', 'Центр', 1000., True, 'ordinary_settlement_record', 0., True),
        ('a', 'Неучтённое село', 200., False, 'ordinary_settlement_record', .01, True),
        ('b', 'Деревня', 50., True, 'ordinary_settlement_record', .02, True),
        ('d', 'Медицинский центр', 300., True, 'ordinary_settlement_record', .03, True),
        ('f', 'Городской ориентир', 1e6, False, 'external_context_nonadditive', .04, True),
        ('x', 'Поселение (часть1)', 10., True, 'ordinary_settlement_record', .005, True),
        ('z', 'Нулевая запись', 0., True, 'ordinary_settlement_record', .006, True),
        ('n', 'Вне исходных точек', 100., True, 'ordinary_settlement_record', .1, False),
    ]:
        rows.append(dict(source_record_id=uid, name=name, region='Регион', district='Район',
                         lat=0., lon=longitude, population_2021=population,
                         population_role=role, budget_population_credit=credit,
                         analysis_origin=active, settlement_type_2021='село'))
    reference = pd.DataFrame(rows)
    ref = reference.set_index('source_record_id')
    destinations = {
        'c': {'school': ('c', 0.), 'medical_basic': ('c', 0.), 'grocery': ('c', 0.)},
        'd': {'medical_basic': ('d', 0.)},
        'f': {'school': ('f', 0.)},
        'a': {'school': ('c', 10.), 'medical_basic': ('d', 8.)},
        'b': {'school': ('f', 4.), 'medical_basic': ('d', 9.), 'grocery': ('c', 5.)},
        'x': {'school': ('c', 6.), 'grocery': ('n', 7.)},
        'z': {'school': ('c', 2.)},
    }
    rows = []
    for origin, needs in destinations.items():
        for family in ['school', 'medical_basic', 'grocery']:
            provider, cost = needs.get(family, (None, np.nan))
            proxy = origin == 'a' and family == 'school'
            rows.append(dict(origin_id=origin, provider_settlement_id=provider,
                             service_family=family, provider_site_id='site-'+provider if provider else None,
                             cost_minutes=cost, admission_limit_minutes=20. if family == 'grocery' else 30.,
                             l0_admitted=provider is not None, local_service_present=provider == origin,
                             scenario_id='daily_20_school30_wb',
                             provider_identity_evidence_tier='dated_cartographic_locality_containment' if proxy else 'legacy_explicit_or_registry',
                             provider_np_identity_basis='hand_specified_source',
                             source_id='test_source', source_year=2026, school_stage_unknown=family == 'school'))
    edges = pd.DataFrame(rows)
    # These centre-member sets are specified directly, without either builder.
    pairs = [('c', 'c', ['school', 'medical_basic', 'grocery'], 0.),
             ('c', 'a', ['school'], 10.), ('c', 'b', ['grocery'], 5.),
             ('d', 'd', ['medical_basic'], 0.), ('d', 'a', ['medical_basic'], 8.),
             ('d', 'b', ['medical_basic'], 9.),
             ('f', 'f', ['school'], 0.), ('f', 'b', ['school'], 4.)]
    members = []
    for centre, origin, families, maximum in pairs:
        q = ref.loc[origin]
        row = q.to_dict()
        row.update(star_id='star-'+centre, centre_settlement_id=centre, origin_id=origin,
                   member_role='centre' if origin == centre else 'direct_surroundings',
                   core_family_count=len(families), core_families_json=json.dumps(sorted(families)),
                   all_families_json=json.dumps(sorted(families)), maximum_directed_minutes=maximum,
                   budget_population_within_star=q.population_2021 if q.budget_population_credit and q.population_role == 'ordinary_settlement_record' else np.nan,
                   positive_whole_spatial=q.population_role == 'ordinary_settlement_record',
                   part_status='unmarked_whole_place_record', coincident_coordinate_requires_review=False,
                   population_is_additive_across_stars=False)
        members.append(row)
    members = pd.DataFrame(members)
    diameter = 6371.0088*math.pi/180*.02
    centres = []
    for uid, own, external, uncredited, budget, proxy, selected in [
        ('c', ['grocery', 'medical_basic', 'school'], 2, 1, 1050., 1, 7),
        ('d', ['medical_basic'], 2, 1, 350., 0, 3),
        ('f', ['school'], 1, 0, 50., 0, 2),
    ]:
        q = ref.loc[uid]
        centres.append(dict(star_id='star-'+uid, centre_settlement_id=uid,
                            centre_name=q['name'], centre_region=q.region,
                            centre_in_analysis_origin=True, centre_unmarked_whole_record=True,
                            centre_positive_population_known=True,
                            centre_population_is_nonadditive_context=uid == 'f',
                            centre_ordinary_spatial_or_nonadditive_context=True,
                            centre_own_selected_core_family_count=len(own),
                            own_known_basic_function_count=len(own),
                            own_known_basic_functions_json=json.dumps(own),
                            type_code='recorded_three_basic_functions' if uid == 'c' else 'recorded_one_basic_function',
                            type_label='Три функции' if uid == 'c' else 'Одна функция',
                            external_participant_count=external, core_diameter_km=diameter,
                            full_service_centre_without_same_three_external_participant=uid == 'c',
                            all_three_core_external_positive_whole=0,
                            positive_uncredited_member_records=uncredited,
                            population_budget_partial=True,
                            population_2021_credited_budget_sum_not_total_population=budget,
                            centre_population_2021_source_value=q.population_2021,
                            centre_population_budget_credit=q.budget_population_credit,
                            selected_links_with_cartographic_ownership=proxy,
                            selected_basic_links=selected,
                            ownership_evidence_class='includes_dated_cartographic_proxy' if proxy else 'retained_literal_or_registry_evidence',
                            level=0, exclusive_partition=False, observed_trips_verified=False,
                            unestablished_functions_are_not_confirmed_absent=True))
    centres = pd.DataFrame(centres)
    links = edges[edges.provider_settlement_id.isin(['c', 'd', 'f']) & edges.l0_admitted].copy()
    links['ownership_uses_cartographic_proxy'] = links.provider_identity_evidence_tier.eq('dated_cartographic_locality_containment')
    return edges, centres, members, links, reference


class IndependentRegistryVerification(unittest.TestCase):
    def test_full_own_set_does_not_require_same_three_external_functions(self):
        result = verify_frames(*fixture(), hold_records=[])
        self.assertEqual(result['registered_centres'], 3)
        self.assertEqual(result['centre_member_pairs'], 8)
        self.assertEqual(result['positive_uncredited_member_rows'], 2)
        self.assertEqual(result['largest_reported_diameters_independently_checked'], 3)
        self.assertFalse(result['ellipsoid_used'])

    def test_uncredited_positive_actor_cannot_disappear(self):
        edges, centres, members, links, ref = fixture()
        members = members[~members.origin_id.eq('a')]
        with self.assertRaisesRegex(ValueError, 'All direct member pairs'):
            verify_frames(edges, centres, members, links, ref, hold_records=[])

    def test_transitive_or_zero_or_source_part_members_are_rejected(self):
        for origin in ['x', 'z', 'n']:
            data = list(fixture())
            bad = data[2].iloc[[0]].copy()
            bad['origin_id'] = origin
            bad['member_role'] = 'direct_surroundings'
            data[2] = pd.concat([data[2], bad], ignore_index=True)
            with self.subTest(origin=origin), self.assertRaisesRegex(ValueError, 'All direct member pairs'):
                verify_frames(*data, hold_records=[])

    def test_centre_anchor_must_occur_exactly_once(self):
        data = list(fixture())
        data[2] = pd.concat([data[2], data[2].iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, 'Duplicate centre-member'):
            verify_frames(*data, hold_records=[])

    def test_own_type_cannot_be_replaced_with_external_support_type(self):
        data = list(fixture())
        data[1].loc[0, 'type_code'] = 'recorded_one_basic_function'
        with self.assertRaisesRegex(ValueError, 'Own-function completeness type'):
            verify_frames(*data, hold_records=[])

    def test_raw_uncredited_population_cannot_be_added_to_budget(self):
        data = list(fixture())
        data[1].loc[0, 'population_2021_credited_budget_sum_not_total_population'] = 1250.
        with self.assertRaisesRegex(ValueError, 'Centre credited budget sum'):
            verify_frames(*data, hold_records=[])

    def test_nonadditive_or_uncredited_budget_must_be_marked_partial(self):
        for centre_row in [0, 2]:
            data = list(fixture())
            data[1].loc[centre_row, 'population_budget_partial'] = False
            with self.subTest(centre=centre_row), self.assertRaisesRegex(ValueError, 'Partial/nonadditive'):
                verify_frames(*data, hold_records=[])

    def test_admission_cannot_exceed_declared_service_cap(self):
        data = list(fixture())
        data[0].loc[data[0].origin_id.eq('a') & data[0].service_family.eq('school'), 'cost_minutes'] = 31.
        with self.assertRaisesRegex(ValueError, 'Declared admission'):
            verify_frames(*data, hold_records=[])

    def test_a_local_flag_cannot_substitute_for_unknown_np_ownership(self):
        data = list(fixture())
        mask = data[0].origin_id.eq('c') & data[0].service_family.eq('school')
        data[0].loc[mask, 'provider_settlement_id'] = None
        with self.assertRaisesRegex(ValueError, 'Known local presence'):
            verify_frames(*data, hold_records=[])

    def test_unreachable_unknown_raw_outcome_need_not_have_a_finite_time(self):
        data = list(fixture())
        mask = data[0].origin_id.eq('a') & data[0].service_family.eq('grocery')
        data[0].loc[mask, 'cost_minutes'] = float('inf')
        result = verify_frames(*data, hold_records=[])
        self.assertEqual(result['registered_centres'], 3)

    def test_wrong_sphere_diameter_is_rejected(self):
        data = list(fixture())
        data[1].loc[0, 'core_diameter_km'] = 200.
        with self.assertRaisesRegex(ValueError, 'Spherical diameter mismatch'):
            verify_frames(*data, hold_records=[])

    def test_reference_metadata_is_checked(self):
        data = list(fixture())
        data[2].loc[1, 'population_2021'] = 999.
        with self.assertRaisesRegex(ValueError, 'Member reference population_2021'):
            verify_frames(*data, hold_records=[])

    def test_cartographic_ownership_is_not_silently_called_literal(self):
        data = list(fixture())
        data[1].loc[0, 'ownership_evidence_class'] = 'retained_literal_or_registry_evidence'
        with self.assertRaisesRegex(ValueError, 'Ownership evidence class'):
            verify_frames(*data, hold_records=[])

    def test_coordinate_hold_reference_identity_and_all_functions_are_checked(self):
        data = list(fixture())
        def record(uid):
            row = data[4].set_index('source_record_id').loc[uid]
            return {'source_record_id': uid, 'reference_fields': {
                key: row[key] for key in ['name', 'settlement_type_2021', 'region', 'district', 'lat', 'lon']}}
        unused = data[4].iloc[-1].copy()
        unused['source_record_id'] = 'u'
        data[4] = pd.concat([data[4], unused.to_frame().T], ignore_index=True)
        safe = record('u')
        result = verify_frames(*data, hold_records=[safe])
        self.assertEqual(result['coordinate_hold_ids_independently_checked'], ['u'])
        for uid in ['a', 'd']:
            with self.assertRaisesRegex(ValueError, 'coordinate-held origin or provider'):
                verify_frames(*data, hold_records=[record(uid)])
        bad = record('n')
        bad['reference_fields']['district'] = 'Чужой район'
        with self.assertRaisesRegex(ValueError, 'reference mismatch'):
            validate_hold_records(data[4], [bad])
        bad = record('n')
        bad['reference_fields']['lat'] = 64.5
        with self.assertRaisesRegex(ValueError, 'reference mismatch'):
            validate_hold_records(data[4], [bad])
        added = data[0].iloc[0].copy()
        added['origin_id'], added['service_family'] = 'u', 'parcel'
        data[0] = pd.concat([data[0], added.to_frame().T], ignore_index=True)
        with self.assertRaisesRegex(ValueError, 'coordinate-held origin or provider'):
            verify_frames(*data, hold_records=[safe])

    def test_coordinate_hold_sources_are_required_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root/'raw.html'
            raw.write_bytes(b'raw primary source')
            (root/'http.json').write_text('{}')
            manifest = root/'holds.json'
            evidence = {'raw_path': 'raw.html', 'metadata_path': 'http.json',
                        'sha256': hashlib.sha256(raw.read_bytes()).hexdigest(), 'http_status': 200}
            manifest.write_text(json.dumps({'records': [{'source_record_id': 'n', 'evidence': [evidence]}]}))
            records, hashes = load_hold_manifest(manifest, root)
            self.assertEqual(records[0]['source_record_id'], 'n')
            self.assertEqual(len(hashes), 3)
            raw.write_bytes(b'altered source')
            with self.assertRaisesRegex(ValueError, 'source proof SHA mismatch'):
                load_hold_manifest(manifest, root)
            with self.assertRaisesRegex(ValueError, 'manifest is missing'):
                load_hold_manifest(root/'missing.json', root)

    def test_unit_sphere_distance_uses_declared_radius_and_handles_missing_points(self):
        self.assertAlmostEqual(sphere_diameter([0., 0., np.nan], [0., 90., 0.]),
                               math.pi*6371.0088/2, places=9)
        self.assertEqual(sphere_diameter([12., 12.], [55., 55.]), 0.)
        self.assertTrue(math.isnan(sphere_diameter([np.nan], [np.nan])))


if __name__ == '__main__':
    unittest.main()
