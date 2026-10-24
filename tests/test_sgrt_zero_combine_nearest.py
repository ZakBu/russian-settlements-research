import unittest,tempfile
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.combine_nearest import combine,run


def frame(costs,year='2021',local=None):
    return pd.DataFrame({'origin_id':['np'+str(i) for i in range(len(costs))],
        'cost_minutes':costs,'service_code':'daily_grocery' if year=='2021' else 'daily_grocery_current_retail_host',
        'provider_site_id':['site'+year if np.isfinite(c) else None for c in costs],
        'known_local_supply':local or [False]*len(costs),'zero_cost_np_assumption':local or [False]*len(costs),
        'source_year':year,'source_id':'old' if year=='2021' else 'fresh',
        'provider_supply_status':'observed' if year=='2021' else 'proxy',
        'provider_historical_supply_needs_current_confirmation':year=='2021',
        'location_precision':'published_coordinates','medical_need_scope':'not_applicable',
        'unconstrained_nearest_cost_minutes':[c+1 if np.isfinite(c) else np.nan for c in costs],
        'unconstrained_nearest_provider_id':['external'+year]*len(costs),
        'route_status':'nearest_known_eligible_provider_site'})


class NearestUnionTests(unittest.TestCase):
    def test_new_positive_evidence_can_improve_stale_direction(self):
        old=frame([30,5]);new=frame([10,15],'2026')
        out=combine([('osm2021',old),('host2026',new)])
        self.assertEqual(out.cost_minutes.tolist(),[10,5])
        self.assertEqual(out.source_year.tolist(),['2026','2021'])
        self.assertEqual(out.provider_supply_status.tolist(),['proxy','observed'])
        self.assertEqual(out.provider_historical_supply_needs_current_confirmation.tolist(),[False,True])
        pd.testing.assert_frame_equal(old,frame([30,5]))
        self.assertFalse(out.union_counts_as_independent_service_channel.any())

    def test_unknown_does_not_become_zero_or_absence(self):
        out=combine([('old',frame([np.nan])),('new',frame([np.nan],'2026'))])
        self.assertTrue(out.cost_minutes.isna().all())
        self.assertTrue(out.union_selected_component.isna().all())
        self.assertTrue(out.provider_site_id.isna().all())
        self.assertFalse(out.known_local_supply.any())

    def test_unknown_first_component_gains_finite_direction(self):
        out=combine([('old',frame([np.nan])),('new',frame([7],'2026'))])
        self.assertEqual(out.cost_minutes.iloc[0],7)
        self.assertEqual(out.source_year.iloc[0],'2026')

    def test_exact_tie_is_deterministic_old_first(self):
        out=combine([('old',frame([5])),('new',frame([5],'2026'))])
        self.assertEqual(out.union_selected_component.iloc[0],'old')
        self.assertEqual(out.union_equal_minimum_component_count.iloc[0],2)

    def test_local_evidence_wins_zero_cost_tie(self):
        out=combine([('old',frame([0])),('new',frame([0],'2026',[True]))])
        self.assertEqual(out.union_selected_component.iloc[0],'new')
        self.assertTrue(out.known_local_supply.iloc[0])
        self.assertTrue(out.zero_cost_np_assumption.iloc[0])

    def test_unconstrained_global_min_does_not_mix_selected_provenance(self):
        old=frame([0],local=[True]);old['unconstrained_nearest_cost_minutes']=100
        new=frame([3],'2026')
        out=combine([('old',old),('new',new)])
        self.assertEqual(out.source_year.iloc[0],'2021')
        self.assertEqual(out.unconstrained_nearest_cost_minutes.iloc[0],100)
        self.assertEqual(out.union_unconstrained_min_cost_minutes.iloc[0],4)
        self.assertEqual(out.union_unconstrained_min_component.iloc[0],'new')

    def test_permuted_or_duplicate_origin_axis_rejected(self):
        old=frame([1,2]);new=frame([2,1],'2026').iloc[::-1]
        with self.assertRaisesRegex(ValueError,'axes'):
            combine([('old',old),('new',new)])
        old['origin_id']='duplicated'
        with self.assertRaisesRegex(ValueError,'Unique'):
            combine([('old',old)])

    def test_origin_coordinate_conflict_rejected(self):
        old=frame([1]);new=frame([2],'2026');old['lat']=45.;new['lat']=46.
        with self.assertRaisesRegex(ValueError,'Origin attribute'):
            combine([('old',old),('new',new)])

    def test_excluded_finite_candidate_is_not_chosen(self):
        old=frame([2]);old['eligible']=False
        new=frame([10],'2026');new['eligible']=True
        out=combine([('old',old),('new',new)])
        self.assertEqual(out.cost_minutes.iloc[0],10)
        out=combine([('old',old)])
        self.assertTrue(out.cost_minutes.isna().iloc[0])
        self.assertTrue(out.provider_site_id.isna().iloc[0])

    def test_unknown_local_cost_cannot_be_invented(self):
        with self.assertRaisesRegex(ValueError,'explicit finite zero'):
            combine([('old',frame([np.nan],local=[True]))])

    def test_raw_component_cannot_be_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw.parquet';frame([1]).to_parquet(path)
            before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'overwrite'):
                run([('old',path)],path)
            self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
