import json
from pathlib import Path
import sys
import tempfile
import runpy
import unittest
from unittest.mock import patch
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero import cloud_primary_demography as cloud


def fixture():
    a=['decline','growth','unchanged','unknown','unknown']
    b=['decline','growth','growth','decline','no_external_rural']
    units=pd.DataFrame({'star_id':[str(x) for x in range(5)],'centre_settlement_id':[str(x) for x in range(5)],
        'centre_name':['Центр '+str(x) for x in range(5)],'lat':[50.]*5,'lon':[40.]*5,
        'is_registered_external_serving_centre':[True]*5})
    classes=units[['star_id','centre_settlement_id']].assign(evidence_mode='accepted_values',
        centre_direction_2002_2021=a,external_primary_rural_state_2002_2021=b)
    classes['descriptive_primary_type_2002_2021']=[x+'__'+y for x,y in zip(a,b)]
    classes['descriptive_primary_type_2002_2010']='unknown__unknown'
    classes['descriptive_primary_type_2010_2021']='unknown__unknown'
    return units,classes


class CloudPrimaryTests(unittest.TestCase):
    def test_all_five_categories_and_exact_description_preserved(self):
        units,classes=fixture();mapped=cloud.site_frame(classes,units)
        self.assertEqual(mapped.value.tolist(),[1,2,3,4,5])
        self.assertEqual(mapped.descriptive_primary_type_2002_2021.tolist(),classes.descriptive_primary_type_2002_2021.tolist())
        self.assertTrue(mapped.evidence_mode.eq('accepted_values').all())
        self.assertFalse(mapped.word_causal_type_established.any())

    def test_missing_or_duplicate_mapped_centre_rejected(self):
        units,classes=fixture()
        with self.assertRaises(ValueError):cloud.site_frame(classes.iloc[:-1],units)
        with self.assertRaises(ValueError):cloud.site_frame(pd.concat([classes,classes.iloc[[0]]]),units)

    def test_control_catches_provenance_column_changes_not_only_counts(self):
        units,classes=fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);units.to_parquet(root/'units.parquet',index=False)
            (root/'summary.json').write_text(json.dumps({'registered_centres':5}))
            for name in cloud.TABLES:
                (classes if name=='primary_centre_demographic_classes' else pd.DataFrame({'id':[1],'quality':['primary']})).to_parquet(root/(name+'.parquet'),index=False)
            before,_=cloud.control(root,root/'units.parquet')
            pd.DataFrame({'id':[1],'quality':['secondary']}).to_parquet(root/'primary_population_evidence.parquet',index=False)
            after,_=cloud.control(root,root/'units.parquet')
            self.assertNotEqual(before['tables']['primary_population_evidence'],after['tables']['primary_population_evidence'])

    def test_published_component_counterexamples_still_pass(self):
        namespace=runpy.run_path(str(cloud.REPO/'tests/test_sgrt_zero_centre_demographic_readout.py'))
        cases=[fn for name,fn in namespace.items() if name.startswith('test_') and callable(fn)]
        self.assertEqual(len(cases),5)
        for case in cases:case()

    def test_existing_draft_cannot_be_overwritten(self):
        with patch.object(cloud,'clean_commit'),patch.object(cloud,'validate_payload',return_value={}),patch.object(cloud,'releases',return_value=[{'tag_name':cloud.TAG,'draft':True}]),patch.object(cloud.subprocess,'run') as command:
            with self.assertRaisesRegex(ValueError,'never be overwritten'):cloud.draft(Path('/unused'),'producer')
            command.assert_not_called()

if __name__=='__main__':unittest.main()
