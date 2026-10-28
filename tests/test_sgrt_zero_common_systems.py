import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from common_systems import anchored_systems, cooperation_diagnostics, CORE


def reference(ids):
    return pd.DataFrame(dict(source_record_id=ids,name=ids,region='r',district='d',lat=50.,lon=40.,
        population_2021=100.,population_role='ordinary_settlement_record',budget_population_credit=True,
        analysis_origin=True))

def scenario(profiles):
    return pd.DataFrame([dict(origin_id=o,service_family=f,provider_settlement_id=p,
        l0_admitted=admitted,cost_minutes=0. if o==p else 5.)
        for o,values in profiles.items() for f,(p,admitted) in zip(CORE,values)])

def centres(ids):
    return pd.DataFrame(dict(centre_settlement_id=ids,star_id=['star-'+i for i in ids],centre_name=ids,
        own_known_basic_function_count=1,lat=50.,lon=40.))

def service(ids,extra=None):
    rows=[dict(centre_settlement_id=i,origin_id=i,member_role='centre') for i in ids]
    rows+=extra or []
    return pd.DataFrame(rows)


class AnchoredTests(unittest.TestCase):
    def test_documented_local_centre_is_not_absorbed_by_its_shop_destination(self):
        e=scenario({'a':[('a',True),('a',True),('b',True)],'b':[('b',True)]*3,
                    'v':[('a',True),('a',True),('b',True)]})
        s=service(['a','b'],[dict(centre_settlement_id='a',origin_id='v',member_role='direct_surroundings')])
        t,summary=anchored_systems(e,reference(['a','b','v']),centres(['a','b']),s)
        m=t['memberships'].set_index('origin_id')
        self.assertEqual(m.loc['a','primary_centre_id'],'a')
        self.assertEqual(m.loc['b','primary_centre_id'],'b')
        self.assertEqual(m.loc['v','primary_centre_id'],'a')
        self.assertEqual(len(t['service_memberships']),len(s))
        self.assertEqual(summary['existing_centres_absorbed'],0)

    def test_anchor_support_is_counted_for_actual_self_not_other_leading_provider(self):
        e=scenario({'a':[('a',True),('b',True),('b',True)],'b':[('b',True)]*3})
        t,_=anchored_systems(e,reference(['a','b']),centres(['a','b']),service(['a','b']))
        a=t['memberships'].set_index('origin_id').loc['a']
        self.assertEqual(a.primary_centre_id,'a')
        self.assertEqual(a.maximum_support_count,2)
        self.assertEqual(a.primary_centre_function_support_count,1)
        self.assertEqual(a.primary_support_fraction_of_all_three_functions,1/3)

    def test_tied_local_provider_keeps_parent_context_without_forced_membership(self):
        e=scenario({'x':[('x',True),('b',True),(None,True)],'b':[('b',True)]*3})
        t,_=anchored_systems(e,reference(['x','b']),centres(['b']),service(['b']))
        x=t['memberships'].set_index('origin_id').loc['x']
        self.assertTrue(pd.isna(x.unit_id))
        context=t['units'].set_index('core_origin_id').loc['x']
        self.assertTrue(context.eligible_as_higher_parent)
        self.assertFalse(context.eligible_as_higher_child)
        self.assertFalse(context.is_registered_external_serving_centre)

    def test_local_self_votes_are_not_dropped_for_a_non_registered_place(self):
        e=scenario({'x':[('x',True),('x',True),('b',True)],'b':[('b',True)]*3})
        t,_=anchored_systems(e,reference(['x','b']),centres(['b']),service(['b']))
        x=t['memberships'].set_index('origin_id').loc['x']
        self.assertTrue(x.unit_id.startswith('local:'))
        self.assertEqual(x.leading_target_id,'x')
        self.assertEqual(x.membership_status,'local_single_site_profile_not_external_centre')
        self.assertEqual(len(t['units'][t['units'].is_registered_external_serving_centre]),1)

    def test_one_known_function_is_provisional_not_three_function_consensus(self):
        e=scenario({'x':[('b',True),(None,False),(None,False)],'b':[('b',True)]*3})
        t,_=anchored_systems(e,reference(['x','b']),centres(['b']),service(['b']))
        x=t['memberships'].set_index('origin_id').loc['x']
        self.assertEqual(x.primary_centre_id,'b')
        self.assertEqual(x.membership_status,'one_known_function_primary_provisional')
        self.assertEqual(x.primary_support_fraction_of_all_three_functions,1/3)
        self.assertFalse(x.all_three_function_identities_known)

    def test_equal_known_targets_and_unknown_third_destination_have_no_winner(self):
        e=scenario({'x':[('a',True),('b',True),(None,True)],'a':[('a',True)]*3,'b':[('b',True)]*3})
        t,_=anchored_systems(e,reference(['x','a','b']),centres(['a','b']),service(['a','b']))
        x=t['memberships'].set_index('origin_id').loc['x']
        self.assertTrue(pd.isna(x.unit_id))
        self.assertEqual(x.membership_status,'distributed_equal_known_support')
        self.assertEqual(x.known_function_count,2)

    def test_missing_outcome_must_not_disappear_from_denominator(self):
        e=scenario({'b':[('b',True)]*3}).iloc[:2]
        with self.assertRaisesRegex(ValueError,'All three outcomes'):
            anchored_systems(e,reference(['b']),centres(['b']),service(['b']))

    def test_cooperation_terminal_with_unknown_functions_is_retained_but_not_complete(self):
        e=scenario({'a':[('a',True),(None,False),(None,False)],'b':[('b',True)]*3})
        t,s=cooperation_diagnostics(e,reference(['a','b']))
        self.assertEqual(s['terminal_components_retained'],2)
        self.assertEqual(s['complete_terminal_cores'],1)
        self.assertFalse(t['cores'].set_index('name').loc['a','complete_three_functions'])

if __name__=='__main__':unittest.main()
