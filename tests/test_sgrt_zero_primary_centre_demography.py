import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from primary_centre_demography import compute


def fixture(rural_type='село'):
    units=pd.DataFrame({'unit_id':['u','context'],'star_id':['s','context'],
        'centre_settlement_id':['a','c'],'is_registered_external_serving_centre':[True,False]})
    memberships=pd.DataFrame({'unit_id':['u','u','context'],'origin_id':['a','b','c'],'is_core':[True,False,True]})
    rows=[]
    for sid,stype,pop in [('a','город',100),('b',rural_type,50),('c','село',20)]:
        r=dict(source_record_id=sid,name=sid,settlement_type_2021=stype,budget_population_credit=True)
        for y,scale in [(2002,1),(2010,1),(2021,2)]:
            r.update({f'population_{y}':pop*scale,f'credit_{y}':True,f'source_record_id_{y}':sid+str(y),
                f'population_value_quality_{y}':'direct_published_census_value',f'population_overlay_applied_{y}':False})
        rows.append(r)
    return units,memberships,pd.DataFrame(rows)


class PrimaryDemographyTests(unittest.TestCase):
    def test_primary_membership_is_exclusive_and_context_not_extra_centre(self):
        _,members,_,classes,summary=compute(*fixture())
        self.assertEqual(summary['registered_centres'],1)
        self.assertEqual(len(members),2)
        self.assertTrue(classes.descriptive_primary_type_2002_2021.eq('growth__growth').all())
        self.assertEqual(summary['untyped_centre_records'],0)

    def test_unknown_external_type_is_not_no_rural(self):
        _,_,_,classes,_=compute(*fixture(None))
        self.assertTrue(classes.external_primary_rural_state_2002_2021.eq('unknown').all())

    def test_urban_external_means_no_rural_not_unchanged(self):
        _,_,_,classes,_=compute(*fixture('город'))
        self.assertTrue(classes.external_primary_rural_state_2002_2021.eq('no_external_rural').all())

    def test_two_intervals_keep_reversal_hidden_by_endpoint_growth(self):
        u,m,r=fixture();r.loc[r.source_record_id.eq('a'),'population_2010']=300
        _,_,_,classes,summary=compute(u,m,r)
        self.assertTrue(classes.centre_direction_2002_2021.eq('growth').all())
        self.assertTrue(classes.centre_two_interval_trajectory_2002_2010_2021.eq('growth__decline').all())
        self.assertEqual(summary['evidence_mode_sensitivity']['2002']['joint_direction_flips_among_known_both'],0)

    def test_secondary_2010_accepted_is_not_primary_observed(self):
        u,m,r=fixture();r.loc[r.source_record_id.eq('b'),'population_value_quality_2010']='secondary_confidentiality_protected_value_exact_scope_unverified'
        _,_,_,classes,summary=compute(u,m,r)
        strict=classes[classes.evidence_mode.eq('strict_direct_observed')].iloc[0]
        accepted=classes[classes.evidence_mode.eq('accepted_values')].iloc[0]
        self.assertEqual(strict.descriptive_primary_type_2010_2021,'growth__unknown')
        self.assertEqual(accepted.descriptive_primary_type_2010_2021,'growth__growth')
        self.assertFalse(summary['raw_effective_population_pair_available'])

if __name__=='__main__':unittest.main()
