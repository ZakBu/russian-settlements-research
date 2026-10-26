import json
import unittest
import pandas as pd

from scripts.sgrt_zero.explicit_locality_identity import ExplicitLocalityIndex, reconcile_explicit_localities


def reference():
    return pd.DataFrame([
        {'source_record_id':'village','name':'Питерка','region':'саратовская','district':'Питерский район','settlement_type_2021':'село','lat':50.,'lon':47.},
        {'source_record_id':'station','name':'Питерка','region':'саратовская','district':'Питерский район','settlement_type_2021':'железнодорожный объект','lat':50.01,'lon':47.},
        {'source_record_id':'homonym','name':'Питерка','region':'тамбовская','district':'Тамбовский район','settlement_type_2021':'село','lat':52.,'lon':42.},
        {'source_record_id':'city','name':'Магнитогорск','region':'челябинская','district':'Магнитогорск','settlement_type_2021':'город','lat':53.4,'lon':59.},
    ])


class ExplicitIdentityTests(unittest.TestCase):
    def setUp(self):
        self.index=ExplicitLocalityIndex(reference())

    def row(self, tags, **kwargs):
        return {'tags_json':json.dumps(tags,ensure_ascii=False),'lat':50.,'lon':47.,**kwargs}

    def test_official_typed_place_resolves_rail_station_and_cross_region_homonyms(self):
        row=self.row({'official_name':'Средняя школа с. Питерка Питерского района Саратовской области'})
        match=self.index.match(row)
        self.assertEqual(match['explicit_locality_source_record_id'],'village')

    def test_explicit_city_requires_boundary_but_needs_no_legacy_bridge(self):
        row=self.row({'addr:city':'Магнитогорск'},lat=53.48,lon=59.)
        match=self.index.match(row)
        self.assertIsNone(match['explicit_locality_source_record_id'])
        self.assertEqual(match['explicit_locality_candidate_source_record_id'],'city')
        row['verified_boundary_source_record_id']='city'
        match=self.index.match(row)
        self.assertEqual(match['explicit_locality_source_record_id'],'city')
        self.assertGreater(match['explicit_locality_distance_km'],5.)

    def test_nearest_point_and_proxy_region_do_not_resolve_homonyms(self):
        row=self.row({'addr:city':'Питерка'},region='саратовская',nearest_reference_region='саратовская')
        self.assertEqual(self.index.match(row)['explicit_locality_identity_status'],'held_ambiguous_literal_identity')

    def test_literal_region_conflict_never_uses_the_nearest(self):
        row=self.row({'addr:city':'Магнитогорск','addr:state':'Саратовская область'})
        self.assertIsNone(self.index.match(row)['explicit_locality_source_record_id'])

    def test_wrong_settlement_type_is_not_discarded(self):
        row=self.row({'official_name':'Школа г. Питерка Питерского района Саратовской области'})
        self.assertIsNone(self.index.match(row)['explicit_locality_source_record_id'])

    def test_district_conflict_is_held(self):
        row=self.row({'official_name':'Школа с. Питерка Тамбовского района Саратовской области'})
        self.assertIsNone(self.index.match(row)['explicit_locality_source_record_id'])

    def test_coordinate_only_rejects_and_never_breaks_an_ambiguous_tie(self):
        row=self.row({'official_name':'Школа с.Питерка Питерского района Саратовской области'},lat=52.,lon=42.)
        self.assertEqual(self.index.match(row)['explicit_locality_identity_status'],'held_literal_coordinate_conflict')

    def test_operator_and_street_names_do_not_assign_places(self):
        row=self.row({'operator':'Школа г. Магнитогорск','addr:street':'Магнитогорская улица'})
        self.assertIsNone(self.index.match(row)['explicit_locality_source_record_id'])

    def test_existing_conflict_is_diagnosed_not_overwritten(self):
        row=self.row({'official_name':'Школа с. Питерка Питерского района Саратовской области'},source_record_id='station')
        result=reconcile_explicit_localities(pd.DataFrame([row]),reference())
        self.assertEqual(result.source_record_id.iloc[0],'station')
        self.assertEqual(result.explicit_locality_identity_status.iloc[0],'held_existing_identity_literal_conflict')
        self.assertEqual(result.tags_json.iloc[0],row['tags_json'])

    def test_person_initial_is_not_a_village_marker(self):
        row=self.row({'official_name':'Школа имени С. Питерка Питерского района Саратовской области'})
        self.assertIsNone(self.index.match(row)['explicit_locality_source_record_id'])

    def test_abbreviated_place_without_space_is_used(self):
        row=self.row({'official_name':'Школа с.Питерка Питерского района Саратовской области'})
        self.assertEqual(self.index.match(row)['explicit_locality_source_record_id'],'village')

    def test_conflicting_literal_districts_are_not_treated_as_alternatives(self):
        row=self.row({'addr:district':'Тамбовский район',
                      'official_name':'Школа с. Питерка Питерского района Саратовской области'})
        self.assertEqual(self.index.match(row)['explicit_locality_identity_status'],
                         'held_conflicting_literal_districts')

    def test_empty_inputs_keep_a_usable_output_schema(self):
        rows=reconcile_explicit_localities(pd.DataFrame(columns=['site_id']),reference())
        self.assertIn('explicit_locality_source_record_id',rows)

    def test_postal_city_conflicting_with_actual_settlement_is_held(self):
        row=self.row({'addr:city':'Магнитогорск'},lat=53.4,lon=59.,
                     verified_boundary_source_record_id='village')
        self.assertEqual(self.index.match(row)['explicit_locality_identity_status'],
                         'held_literal_boundary_conflict')

    def test_nearby_postal_city_without_boundary_is_still_only_candidate(self):
        row=self.row({'addr:city':'Магнитогорск'},lat=53.401,lon=59.)
        match=self.index.match(row)
        self.assertIsNone(match['explicit_locality_source_record_id'])
        self.assertEqual(match['explicit_locality_identity_status'],
                         'candidate_address_locality_needs_boundary_confirmation')

    def test_real_vorsha_and_saltyn_postal_city_counterexamples_do_not_become_city_schools(self):
        ref=pd.DataFrame([
            {'source_record_id':'vladimir','name':'Владимир','region':'владимирская',
             'district':'Владимир','settlement_type_2021':'город','lat':56.13,'lon':40.40},
            {'source_record_id':'uryupinsk','name':'Урюпинск','region':'волгоградская',
             'district':'Урюпинск','settlement_type_2021':'город','lat':50.80,'lon':42.00},
        ])
        index=ExplicitLocalityIndex(ref)
        # Literal name/address subsets from the frozen source cards. A postal
        # city and even a globally unique name are not geographical containment.
        rows=[self.row({'addr:city':'Владимир','name':'Воршинская Средняя школа'},
                       lat=56.04873624444444,lon=40.07062625555555),
              self.row({'addr:city':'Урюпинск','name':'МБОУ Салтынская СОШ'},
                       lat=51.0470304,lon=41.9097771)]
        for row in rows:
            self.assertIsNone(index.match(row)['explicit_locality_source_record_id'])
            self.assertEqual(index.match(row)['explicit_locality_identity_status'],
                             'candidate_address_locality_needs_boundary_confirmation')

    def test_branch_parent_village_is_not_the_physical_branch_owner(self):
        for name in ['Тайдаковский филиал СОШ с. Питерка',
                     'Сельская школа. Структурное подразделение СОШ с.Питерка',
                     'ОСП МОБУ «СОШ им.Ф.В.Ванина в с.Питерка»']:
            row=self.row({'name':name,'addr:state':'Саратовская область'})
            match=self.index.match(row)
            self.assertIsNone(match['explicit_locality_source_record_id'])
            self.assertEqual(match['explicit_locality_identity_status'],
                             'held_parent_institution_locality_for_branch')

    def test_same_branch_literal_needs_independent_boundary_confirmation(self):
        row=self.row({'name':'Филиал СОШ с. Питерка','addr:state':'Саратовская область'},
                     verified_boundary_source_record_id='village')
        self.assertEqual(self.index.match(row)['explicit_locality_source_record_id'],'village')

    def test_joined_honorific_initials_do_not_assign_surname_settlements(self):
        ref=pd.DataFrame([
            {'source_record_id':'wrong-k','name':'Королёва','region':'московская',
             'district':'Ивановский','settlement_type_2021':'посёлок','lat':55.,'lon':37.},
            {'source_record_id':'wrong-p','name':'Пушкина','region':'московская',
             'district':'Ивановский','settlement_type_2021':'село','lat':55.,'lon':37.},
        ])
        index=ExplicitLocalityIndex(ref)
        for name in ['Муниципальная школа имени С.П. Королёва',
                     'Школа им. С.П. Королёва',
                     'Школа им.С.П.Королёва',
                     'Школа им П.Королёва',
                     'Школа имени Героя Советского Союза П.Королёва',
                     'Школа им А.С.Пушкина',
                     'Школа «С.П. Королёва»',
                     'Школа «П. Королёва»']:
            with self.subTest(name=name):
                row=self.row({'official_name':name},lat=55.,lon=37.)
                self.assertIsNone(index.match(row)['explicit_locality_source_record_id'])


if __name__=='__main__':
    unittest.main()
