import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_zero'))
from hierarchy import higher_candidates_reference as higher_candidates
from higher_candidates_fast import higher_candidates_fast
from test_sgrt_zero_hierarchy import edges,reference

class CandidateEquivalenceTests(unittest.TestCase):
    def equivalent(self,m,h,r):
        pd.testing.assert_frame_equal(higher_candidates(m,h,r),higher_candidates_fast(m,h,r))

    def test_random_split_partial_multiple_scenarios_and_json(self):
        rng=np.random.default_rng(47)
        ids=[str(x) for x in range(8)];r=reference(ids)
        for iteration in range(35):
            m=pd.DataFrame([{'unit_id':'u'+str(rng.integers(0,4)),'origin_id':o,'scenario_id':s} for s in ['z','a'] for o in ids])
            h=edges({o:{f: (str(rng.integers(0,8)) if rng.random()<.7 else None) for f in ['hospital','college']} for o in ids},'higher_admitted')
            h['source_id']=[None if rng.random()<.2 else 'src'+str(rng.integers(0,3)) for _ in range(len(h))]
            h['territorial_merge_admitted']=[bool(rng.integers(0,2)) for _ in range(len(h))]
            h['territorial_guard_basis']=[None if rng.random()<.2 else 'basis'+str(rng.integers(0,3)) for _ in range(len(h))]
            h['parent_target_key']=[('efua:x' if rng.random()<.4 else None) for _ in range(len(h))]
            h['parent_target_kind']=['external_functional_area' if x else None for x in h.parent_target_key]
            self.equivalent(m,h,r)

    def test_numeric_year_coercion_with_unmatched_members(self):
        m=pd.DataFrame({'unit_id':['u','u','v'],'origin_id':['a','b','c'],'scenario_id':'test'})
        h=edges({'a':{'physician':'d'}},'higher_admitted',True)
        self.equivalent(m,h,reference())

    def test_nullable_guard_skipna_matches_original(self):
        m=pd.DataFrame({'unit_id':['u','u'],'origin_id':['a','b'],'scenario_id':'test'})
        h=edges({'a':{'physician':'d'},'b':{'physician':'d'}},'higher_admitted')
        for guard in [pd.Series([True,pd.NA],dtype='boolean'),pd.Series([True,pd.NA],dtype=object),pd.Series([1,None],dtype=object)]:
            h['territorial_merge_admitted']=guard
            self.equivalent(m,h,reference())

    def test_unknown_site_identity_and_all_not_admitted(self):
        m=pd.DataFrame({'unit_id':['u','u'],'origin_id':['a','b'],'scenario_id':'test'})
        h=edges({'a':{'physician':'d'},'b':{'physician':'d'}},'higher_admitted')
        h['provider_settlement_id']=None
        self.equivalent(m,h,reference())
        h['higher_admitted']=False
        self.equivalent(m,h,reference())

    def test_null_members_and_categorical_unused_child(self):
        m=pd.DataFrame({'unit_id':['u',None],'origin_id':['a','b'],'scenario_id':'test'})
        h=edges({'a':{'physician':'d'},'b':{'physician':'d'}},'higher_admitted')
        self.equivalent(m,h,reference())
        m['unit_id']=pd.Categorical(m.unit_id,categories=['u','unused'])
        self.equivalent(m,h,reference())

    def test_rejections_preserved(self):
        m=pd.DataFrame({'unit_id':['u'],'origin_id':['a'],'scenario_id':'test'})
        h=edges({'a':{'physician':'d'}},'higher_admitted')
        for broken in [pd.concat([h,h]),h.assign(parent_target_key='efua:bad'),h.assign(provider_settlement_id='outside')]:
            with self.assertRaises(ValueError):higher_candidates_fast(m,broken,reference())
