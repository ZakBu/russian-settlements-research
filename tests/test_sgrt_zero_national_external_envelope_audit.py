import unittest
import pandas as pd
from shapely.geometry import box
from scripts.sgrt_zero.national_external_envelope_audit import point_envelopes,footprint_union,audit_units


class NationalEnvelopeTests(unittest.TestCase):
    def inputs(self):
        ref=pd.DataFrame({'source_record_id':['c','near','far'],'name':['C','N','F'],
            'lat':[0.5,0.6,5.],'lon':[0.5,0.6,5.],'population_2021':[100.,10.,10.]})
        units=pd.DataFrame({'unit_id':['u'],'core_origin_id':['c'],'name':['C'],
            'unit_role':['external_serving_anchor'],'is_registered_external_serving_centre':[True]})
        members=pd.DataFrame({'origin_id':['c','near','far'],'unit_id':['u','u','other'],
            'positive_whole_origin':[True,True,True]})
        polygons=pd.DataFrame({'eFUA_ID':['a'],'geometry_crs':['EPSG:4326'],'geometry_wkb':[box(0,0,1,1).wkb]})
        return ref,units,members,polygons

    def test_original_functional_member_outside_primary_is_never_omitted(self):
        ref,units,members,polygons=self.inputs()
        stars=pd.DataFrame({'centre_settlement_id':['c'],'origin_id':['far']})
        raw,positive=footprint_union(units,members,stars)
        pairs,known=point_envelopes(ref,polygons)
        audit,candidates=audit_units(units,raw,positive,pairs,known,ref)
        self.assertEqual(len(positive[positive.unit_id.eq('u')]),3)
        self.assertEqual(audit.compatibility_status.iloc[0],'core_inside_but_child_outside_every_core_envelope')
        self.assertFalse(candidates.complete_input_compatibility.any())

    def test_boundaries_and_multiple_overlapping_envelopes_survive(self):
        ref,units,members,polygons=self.inputs()
        ref.loc[0,['lat','lon']]=[0.,0.]
        polygons=pd.concat([polygons,pd.DataFrame({'eFUA_ID':['b'],'geometry_crs':['EPSG:4326'],
            'geometry_wkb':[box(-1,-1,2,2).wkb]})],ignore_index=True)
        pairs,known=point_envelopes(ref,polygons)
        self.assertEqual(set(pairs.loc[pairs.origin_id.eq('c'),'external_efua_id']),{'a','b'})
        raw,positive=footprint_union(units,members,pd.DataFrame(columns=['centre_settlement_id','origin_id']))
        audit,candidates=audit_units(units,raw,positive,pairs,known,ref)
        self.assertEqual(audit.compatible_complete_input_envelope_count.iloc[0],2)
        self.assertEqual(len(candidates),2)

    def test_missing_positive_coordinates_never_become_confirmed_outside_or_inside(self):
        ref,units,members,polygons=self.inputs();ref.loc[1,'lat']=float('nan')
        raw,positive=footprint_union(units,members,pd.DataFrame(columns=['centre_settlement_id','origin_id']))
        pairs,known=point_envelopes(ref,polygons)
        audit,candidates=audit_units(units,raw,positive,pairs,known,ref)
        self.assertEqual(audit.positive_member_coordinates_unknown.iloc[0],1)
        self.assertEqual(audit.compatibility_status.iloc[0],'unknown_positive_demand_or_coordinates')
        self.assertFalse(candidates.complete_input_compatibility.any())

    def test_context_core_is_checked_even_when_assigned_to_other_primary_unit(self):
        ref,units,members,polygons=self.inputs();ref.loc[0,['lat','lon']]=[5.,5.]
        members.loc[0,'unit_id']='other'
        raw,positive=footprint_union(units,members,pd.DataFrame(columns=['centre_settlement_id','origin_id']))
        self.assertIn('c',set(positive.loc[positive.unit_id.eq('u'),'origin_id']))
        pairs,known=point_envelopes(ref,polygons)
        audit,_=audit_units(units,raw,positive,pairs,known,ref)
        self.assertEqual(audit.compatibility_status.iloc[0],'no_external_envelope')

    def test_unknown_population_is_not_silently_ignored_as_no_demand(self):
        ref,units,members,polygons=self.inputs();ref.loc[1,'population_2021']=float('nan');members.loc[1,'positive_whole_origin']=False
        raw,positive=footprint_union(units,members,pd.DataFrame(columns=['centre_settlement_id','origin_id']))
        pairs,known=point_envelopes(ref,polygons)
        audit,candidates=audit_units(units,raw,positive,pairs,known,ref)
        self.assertEqual(audit.unknown_population_records_not_assumed_positive.iloc[0],1)
        self.assertFalse(candidates.complete_input_compatibility.any())

    def test_known_zero_population_core_does_not_pass_empty_footprint(self):
        ref,units,members,polygons=self.inputs()
        ref.loc[:,'population_2021']=0.
        members.loc[:,'positive_whole_origin']=False
        raw,positive=footprint_union(units,members,pd.DataFrame(columns=['centre_settlement_id','origin_id']))
        pairs,known=point_envelopes(ref,polygons)
        audit,candidates=audit_units(units,raw,positive,pairs,known,ref)
        self.assertEqual(audit.compatibility_status.iloc[0],'no_positive_whole_demand')
        self.assertEqual(audit.compatible_complete_input_envelope_count.iloc[0],0)
        self.assertFalse(candidates.complete_input_compatibility.any())


if __name__=='__main__':unittest.main()
