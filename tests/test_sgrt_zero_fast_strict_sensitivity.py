import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from centre_stars import build_centre_stars
from fast_strict_sensitivity import strict_only,rescreen_main_edges
from tests.test_sgrt_zero_centre_stars import edges,reference


class FastStrictTests(unittest.TestCase):
    def assert_equal(self,e,r=None):
        r=reference() if r is None else r
        full,_=build_centre_stars(e,r);fast,summary=strict_only(e,r)
        for key in fast:
            left=full[key].sort_values(['star_id']+(['origin_id'] if 'origin_id' in full[key] else [])).reset_index(drop=True)
            right=fast[key].sort_values(['star_id']+(['origin_id'] if 'origin_id' in fast[key] else [])).reset_index(drop=True)
            # Full-context counts and diameters include weak satellites and are
            # intentionally not used to describe the strict subset. Every
            # strict-specific value and actual strict member is identical.
            if key=='strict_three_core_stars':
                columns=['star_id','centre_settlement_id','strict_member_count','strict_external_member_count',
                    'strict_geodesic_diameter_km','strict_population_2021_credited_sum',
                    'any_strict_coordinate_review','any_strict_road_endpoint_review',
                    'strict_road_component_quality_unknown','strict_any_component_lt100_diagnostic',
                    'strict_school_stage_unknown_records']
                left=left[columns];right=right[columns]
            pd.testing.assert_frame_equal(left,right,check_dtype=bool(len(left)))
        self.assertTrue(summary['no_full_functional_star_counts_computed'])

    def test_positive_with_weak_unrelated_stars_and_parcel(self):
        self.assert_equal(edges({'a':{'medical_basic':'c','school':'c','grocery':'c','parcel_pickup':'c'},
            'b':{'school':'c','grocery':'d'},'c':{'medical_basic':'c','school':'c','grocery':'c'},
            'd':{'medical_basic':'d','grocery':'d'}}))

    def test_missing_own_family_empty_strict_schema(self):
        self.assert_equal(edges({'a':{'medical_basic':'c','school':'c','grocery':'c'},'c':{'medical_basic':'c','school':'c'}}))

    def test_source_part_external_and_unknown_role_centre(self):
        e=edges({'a':{'medical_basic':'c','school':'c','grocery':'c'},'c':{'medical_basic':'c','school':'c','grocery':'c'}})
        r=reference();r.loc[r.source_record_id=='a','name']='A (часть 1)';self.assert_equal(e,r)
        r=reference();r.loc[r.source_record_id=='c','population_role']=None;self.assert_equal(e,r)

    def test_all_unknown_np_and_all_not_admitted(self):
        e=edges({'a':{'school':None}});self.assert_equal(e)
        e=edges({'a':{'medical_basic':'c','school':'c','grocery':'c'}});e['l0_admitted']=False;self.assert_equal(e)

    def test_saved_outcomes_are_rescreened_for_actual_travel_limits(self):
        e=edges({'a':{'medical_basic':'c','school':'c','grocery':'c'},
                 'c':{'medical_basic':'c','school':'c','grocery':'c'}})
        e['local_service_present']=e.origin_id.eq(e.provider_settlement_id)
        e['provider_grades_known']=False;e['routable_external_provider_seeds']=1
        e['known_offer_records']=1;e['origin_road_endpoint_accepted']=True
        e.loc[e.origin_id.eq('a'),'cost_minutes']=12.
        e.loc[e.origin_id.eq('c'),'cost_minutes']=0.
        r=reference()
        _,main=strict_only(rescreen_main_edges(e,'daily_20_school30_wb'),r)
        _,close=strict_only(rescreen_main_edges(e,'daily_10_school15_wb'),r)
        _,wide=strict_only(rescreen_main_edges(e,'daily_30_school30_wb'),r)
        self.assertEqual(main['strict_three_core_model_screened_stars'],1)
        self.assertEqual(close['strict_three_core_model_screened_stars'],0)
        self.assertEqual(wide['strict_three_core_model_screened_stars'],1)
        e.loc[e.origin_id.eq('a'),'cost_minutes']=25.
        _,main=strict_only(rescreen_main_edges(e,'daily_20_school30_wb'),r)
        _,wide=strict_only(rescreen_main_edges(e,'daily_30_school30_wb'),r)
        self.assertEqual(main['strict_three_core_model_screened_stars'],0)
        self.assertEqual(wide['strict_three_core_model_screened_stars'],1)

    def test_two_possible_centres_never_merge_chain(self):
        r=reference();extra=r.iloc[[0]].copy();extra['source_record_id']='z';extra['name']='Z';extra['lat']=51.;r=pd.concat([r,extra],ignore_index=True)
        self.assert_equal(edges({'a':{'medical_basic':'c','school':'c','grocery':'c'},
            'c':{'medical_basic':'c','school':'c','grocery':'c'},
            'b':{'medical_basic':'d','school':'d','grocery':'d'},
            'd':{'medical_basic':'d','school':'d','grocery':'d'},'z':{'school':'a'}}),r)


if __name__=='__main__':unittest.main()
