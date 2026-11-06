import json
import unittest

import numpy as np
import pandas as pd

from scripts.sgrt_saratov.system_structure import build_memberships, describe_functions, stable_id, validate_medical_relations, apply_identity_overrides


class FixedDocumentedFrameworks(unittest.TestCase):
    def setUp(self):
        self.roster=pd.DataFrame([{'source_record_id':i,'name':i,'population_2021':p,'district_norm':'петровский'}
            for i,p in [('A',100),('B',200),('C',300),('D',50),('Z',0)]])
        self.document=pd.DataFrame([{'origin_id':i,'campus_id':core,'source_id':'document',
            'source_url':'https://example.org/document','relation_type':'admission'}
            for i,core in [('A','B'),('B','B'),('D','B'),('Z','B'),('C','C')]])
        rows=[]
        choices={('A','school'):(['np:B'],5),('B','school'):(['np:B'],0),
            ('D','school'):(['np:B'],6),('C','school'):(['np:C'],0),
            ('A','medical_basic'):(['np:A'],0),('B','medical_basic'):(['np:C'],10),
            ('Z','medical_basic'):(['np:D'],4),
            ('A','grocery'):(['np:B','np:C'],8),('D','grocery'):(['site:unknown-locality'],2)}
        for i in self.roster.source_record_id:
            for family in ['school','medical_basic','grocery']:
                keys,cost=choices.get((i,family),([],np.nan))
                rows.append({'origin_id':i,'family':family,'evidence_scenario':'all_dated_known',
                    'coequal_primary_keys_json':json.dumps(keys),'cost_minutes':cost,
                    'known_local_supply':keys==['np:'+i]})
        self.links=pd.DataFrame(rows)
        self.systems,self.members,self.unresolved=build_memberships(self.document,self.roster)
        self.outcomes,self.edges,self.roles=describe_functions(self.systems,self.members,self.links)
        self.bid=stable_id('documented_school_assignment_2025','B')
        self.cid=stable_id('documented_school_assignment_2025','C')

    def outcome(self,origin,family):
        return self.outcomes[self.outcomes.system_id.eq(self.bid)&self.outcomes.origin_id.eq(origin)
            &self.outcomes.family.eq(family)].iloc[0]

    def test_external_centre_dependency_never_adds_members_transitively(self):
        self.assertEqual(set(self.members.loc[self.members.system_id.eq(self.bid),'source_record_id']),{'A','B','D','Z'})
        self.assertEqual(set(self.members.loc[self.members.system_id.eq(self.cid),'source_record_id']),{'C'})
        self.assertEqual(self.outcome('B','medical_basic').outcome_status,'external')

    def test_local_function_survives_inside_school_framework_and_zero_origin_cannot_create_subcentre(self):
        self.assertEqual(self.outcome('A','medical_basic').outcome_status,'own')
        received=self.roles[self.roles.system_id.eq(self.bid)]
        self.assertNotIn('D',set(received.source_record_id))
        self.assertIn('B',set(received.source_record_id))

    def test_equal_internal_and_external_options_remain_mixed(self):
        result=self.outcome('A','grocery')
        self.assertEqual(result.outcome_status,'coequal_mixed_scope')
        self.assertEqual(set(json.loads(result.destination_scopes_json)),{'core','external'})
        self.assertEqual(result.coequal_destination_count,2)

    def test_unknown_accessibility_and_unknown_site_identity_do_not_become_local_zero(self):
        missing=self.outcome('D','medical_basic')
        self.assertEqual(missing.outcome_status,'accessibility_unknown')
        self.assertTrue(pd.isna(missing.cost_minutes))
        self.assertEqual(missing.coequal_destination_count,0)
        site=self.outcome('D','grocery')
        self.assertEqual(site.outcome_status,'physical_site_np_unresolved')
        self.assertEqual(site.cost_minutes,2)
        held=self.edges[self.edges.origin_id.eq('D')&self.edges.family.eq('grocery')]
        self.assertTrue(held.destination_np_id.isna().all())

    def test_all_unknown_outcomes_are_retained_with_empty_destination_schema(self):
        links=self.links.copy()
        links['cost_minutes']=np.nan
        links['coequal_primary_keys_json']='[]'
        links['known_local_supply']=np.nan
        outcomes,edges,roles=describe_functions(self.systems,self.members,links)
        self.assertEqual(len(outcomes),len(self.members)*3)
        self.assertTrue(outcomes.outcome_status.eq('accessibility_unknown').all())
        self.assertFalse(outcomes.known_local_supply.any())
        self.assertTrue(edges.empty)
        self.assertIn('destination_scope',edges)
        self.assertTrue(roles.empty)

    def test_repeated_document_mentions_do_not_double_count_members(self):
        duplicate=pd.concat([self.document,self.document.iloc[[0]]],ignore_index=True)
        systems,members,_=build_memberships(duplicate,self.roster)
        self.assertEqual(len(members),len(self.members))
        self.assertEqual(len(systems),len(self.systems))

    def test_known_identity_but_nonoperating_source_stays_held_and_marks_partial_membership(self):
        medical=pd.DataFrame([{'origin_id':i,'core_id':'B','source_id':'medical_document',
            'source_url':'https://example.org/medical','relation_type':'service_territory',
            'accepted':accepted,'member_role':'core_self' if i=='B' else 'external'}
            for i,accepted in [('B',True),('A',True),('D',False)]])
        systems,members,held=build_memberships(medical,self.roster,
            document_basis='documented_medical_assignment_2025',document_function='medical_basic',
            core_column='core_id',reference_period='active_description')
        self.assertEqual(set(members.source_record_id),{'A','B'})
        self.assertEqual(len(held),1)
        self.assertFalse(systems.iloc[0].documented_membership_complete)
        # An all-held historical/planned group is inventory, not a failure and not a framework.
        systems,members,held=build_memberships(medical.assign(accepted=False),self.roster,
            core_column='core_id')
        self.assertTrue(systems.empty)
        self.assertTrue(members.empty)
        self.assertEqual(len(held),3)

    def test_new_medical_document_is_checked_without_changing_archived_choices(self):
        document=pd.DataFrame([{'origin_id':'A','core_id':'B','family':'medical_basic','accepted':True}])
        before=self.links.copy(deep=True)
        result=validate_medical_relations(document,self.roster,self.links)
        self.assertEqual(result.iloc[0].validation_status,'different_model_destination')
        self.assertTrue(result.iloc[0].is_external_inhabited_validation)
        self.assertFalse(result.iloc[0].document_used_to_enrich_this_model_inventory)
        pd.testing.assert_frame_equal(self.links,before)

    def test_reviewed_identity_overlay_preserves_raw_source_and_forbids_name_substitution(self):
        source=pd.DataFrame([{'source_id':'new_document','section_number':1,'member_literal':'A',
            'origin_id':None,'accepted':False,'identity_status':'held_kind_not_explicit',
            'member_kind':None,'rayon':'Петровский',
            'member_role':'documented_external_member_not_assumed_fap_host',
            'reference_time':'document_2025_description_active_not_independently_verified2026'}])
        overrides=pd.DataFrame([{'source_id':'new_document','section_number':1,'member_literal':'A',
            'origin_id':'A','identity_status':'explicit_district_unique_name_kind_unknown','reason':'reviewed exact identity'}])
        mapped=apply_identity_overrides(source,overrides,self.roster)
        self.assertFalse(source.iloc[0].accepted)
        self.assertTrue(mapped.iloc[0].accepted)
        self.assertFalse(mapped.iloc[0].raw_identity_accepted)
        self.assertTrue(mapped.iloc[0].identity_override_applied)
        with self.assertRaises(ValueError):
            apply_identity_overrides(source,overrides.assign(origin_id='D'),self.roster)
        with self.assertRaises(ValueError):
            apply_identity_overrides(source.assign(reference_time='administrative_attachment_site_building_not_operating'),overrides,self.roster)
        with self.assertRaises(ValueError):
            apply_identity_overrides(source.assign(rayon='Другой'),overrides,self.roster)


if __name__=='__main__':unittest.main()
