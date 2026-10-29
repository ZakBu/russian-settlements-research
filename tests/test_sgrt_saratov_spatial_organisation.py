import unittest
import numpy as np
import pandas as pd
from scripts.sgrt_saratov.spatial_organisation import point_maxima, scale_changes, cross_scale_correspondence, scale_neighbourhood_maxima


def field(source, value, scale=10):
    return dict(source_record_id=source, kernel='gaussian', half_time=scale,
                include_self=True, value=value, accepted_mass_field_upper=value)


class MultiscaleGeography(unittest.TestCase):
    def test_external_halo_can_disprove_regional_peak(self):
        roster=pd.DataFrame({'source_record_id':['a'],'name':['A']})
        edges=pd.DataFrame([dict(origin_id='a',destination_id=s,in_k3=True,in_k6=True) for s in ['outside','out2','out3']])
        out=point_maxima(pd.DataFrame([field('a',4)]),pd.DataFrame([field('outside',9),field('out2',1),field('out3',2)]),edges,roster)
        self.assertTrue(out.loc[out.neighbour_count.eq(3),'point_comparison_testable'].all())
        self.assertFalse(out.sampled_point_maximum.any())
        absent=point_maxima(pd.DataFrame([field('a',4)]),pd.DataFrame(columns=pd.DataFrame([field('a',4)]).columns),edges,roster)
        self.assertFalse(absent.point_comparison_testable.any())

    def test_isolated_zero_is_not_a_centre(self):
        roster=pd.DataFrame({'source_record_id':['a'],'name':['A']})
        edges=pd.DataFrame(columns=['origin_id','destination_id','in_k3','in_k6'])
        f=pd.DataFrame([field('a',0)])
        result=point_maxima(f,f.iloc[:0],edges,roster)
        self.assertFalse(result.sampled_point_maximum.any())

    def test_increasing_peak_count_is_retained(self):
        roster=pd.DataFrame({'source_record_id':['a','b'],'name':['A','B']})
        peaks=pd.DataFrame([dict(kernel='gaussian',include_self=True,neighbour_count=3,
            half_time=h,source_record_id=s,sampled_point_maximum=p)
            for h,s,p in [(10,'a',True),(10,'b',False),(20,'a',True),(20,'b',True)]])
        changes,intervals=scale_changes(peaks,roster)
        self.assertEqual(changes.loc[changes.source_record_id.eq('b'),'event'].tolist(),['appeared'])
        self.assertEqual(intervals.peak_count.tolist(),[1,2])

    def test_cross_scale_comparison_keeps_direction_and_ties(self):
        roster=pd.DataFrame({'source_record_id':['a','b','c'],'name':['A','B','C']})
        peaks=pd.DataFrame([dict(kernel='gaussian',include_self=True,neighbour_count=3,
            half_time=h,source_record_id=s,sampled_point_maximum=p)
            for h,s,p in [(10,'a',True),(10,'b',False),(10,'c',False),
                          (20,'a',False),(20,'b',True),(20,'c',True)]])
        costs=np.array([[0,8,8],[2,0,3],[20,3,0]],float)
        pairs=cross_scale_correspondence(peaks,roster,costs)
        self.assertEqual(set(pairs.comparison_peak_id),{'b','c'})
        self.assertEqual(pairs.directed_minutes.tolist(),[8,8])
        self.assertFalse(pairs.is_parent_system_assignment.any())


class GrowingNeighbourhood(unittest.TestCase):
    def test_farther_stronger_point_disproves_a_small_neighbourhood_peak(self):
        roster=pd.DataFrame({'source_record_id':['a','b','c']})
        costs=np.array([[0,2,8],[2,0,7],[8,7,0]],float)
        f=pd.DataFrame([field('a',5),field('b',1),field('c',9)])
        out=scale_neighbourhood_maxima(f,roster,costs,np.array([50.,50.,50.]),factors=(.5,1.))
        a=out[out.source_record_id.eq('a')]
        self.assertEqual(a.regional_scale_maximum.tolist(),[True,False])

    def test_unchecked_external_competitor_prevents_complete_peak_claim(self):
        roster=pd.DataFrame({'source_record_id':['a','b']})
        f=pd.DataFrame([field('a',9),field('b',1)])
        out=scale_neighbourhood_maxima(f,roster,np.array([[0.,2.],[2.,0.]]),np.array([4.,50.]),factors=(1.,))
        a=out[out.source_record_id.eq('a')].iloc[0]
        self.assertTrue(a.regional_scale_maximum)
        self.assertFalse(a.complete_routable_point_scale_maximum)


if __name__=='__main__':unittest.main()
