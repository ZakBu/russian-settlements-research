import sys
import unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from audit_upper_research import census_bounds,envelope_intersections,temporal_values


class IndependentUpperAuditTests(unittest.TestCase):
    def test_corrupted_census_upper_is_detected(self):
        frame=pd.DataFrame([dict(population_base_source_record_id='NP1',name='Fixture',
            employed_age15_72=100,same_subject=80,same_np=70,outside_np_known=25,
            unknown_workplace=5,named_parent_share_upper_bound=.20,
            commuting_threshold_scenario=.15,any_named_parent_at_threshold_ruled_out_by_2010_margin=False,
            observed_named_parent_identified=False)])
        self.assertEqual(census_bounds(frame)['upper_bound_mismatches'],0)
        frame.loc[0,'named_parent_share_upper_bound']=.25
        with self.assertRaisesRegex(ValueError,'conservative upper mismatch'):
            census_bounds(frame)

    def test_whole_child_outside_cannot_pass_from_core_alone(self):
        audit=pd.DataFrame([dict(unit_id='u',core_origin_id='core',
            unknown_population_records_not_assumed_positive=0,positive_member_coordinates_unknown=0,
            core_coordinates_known=True,compatible_complete_input_envelope_count=0,
            whole_known_positive_envelope_count=0,external_envelope_is_independent_validation=False,
            empirical_sgrt_level_assigned=False,compatibility_status='core_inside_child_outside')])
        pairs=pd.DataFrame(dict(origin_id=['core'],external_efua_id=[1]))
        members=pd.DataFrame(dict(unit_id=['u','u'],origin_id=['core','remote']))
        candidates=pd.DataFrame([dict(unit_id='u',external_efua_id=1,required_positive_whole_records=2,
            required_positive_whole_inside=1,required_positive_whole_outside_or_unknown=1,
            complete_input_compatibility=False)])
        self.assertEqual(envelope_intersections(audit,candidates,pairs,members)['candidate_pairs_checked'],1)
        audit.loc[0,'compatible_complete_input_envelope_count']=1
        with self.assertRaisesRegex(ValueError,'Whole-envelope intersection mismatch'):
            envelope_intersections(audit,candidates,pairs,members)

    def test_single_corrupted_workforce_value_is_detected(self):
        comparison=pd.DataFrame(dict(oktmo=['a','b','c'],workforce_numeric_first=[10.,20.,30.],
            workforce_numeric_last=[11.,22.,33.],territorial_boundary_equivalence_verified=False,
            difference_is_net_commuting=False))
        raw=pd.DataFrame([dict(indicator_code='Y48423005',indicator_period='Январь-декабрь',
            okved2='Всего по обследуемым видам экономической деятельности',year=year,
            oktmo=code,indicator_value=value,indicator_unit='Человек')
            for year,values in [(2021,[10.,20.,30.]),(2025,[11.,22.,33.])]
            for code,value in zip(['a','b','c'],values)])
        summary=dict(first_year=2021,last_year=2025,same_code_observed_both=3,
            recorded_partial_workforce_stability={'same_code_numeric_both':{
                'spearman_recorded_partial_workforce_2021_2025':1.}})
        self.assertEqual(temporal_values(raw,comparison,summary)['source_value_mismatches'],0)
        comparison.loc[1,'workforce_numeric_last']=23.
        with self.assertRaisesRegex(ValueError,'Raw annual workforce value mismatch: 2025'):
            temporal_values(raw,comparison,summary)


if __name__=='__main__':unittest.main()
