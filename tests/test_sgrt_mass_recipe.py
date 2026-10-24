"""Portability and source-boundary regressions for the national recipe."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE=Path(__file__).resolve().parents[1]/'scripts/sgrt_mass/reproduce.py'
spec=importlib.util.spec_from_file_location('mass_recipe_under_test',MODULE)
recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)


class NationalRecipeTests(unittest.TestCase):
    def test_plan_requires_each_source_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'catalog.json'
            path.write_text(json.dumps({'files':[{'path':'graph/a','profiles':['core'],'blob':'x','bytes':5}],
                'objects':{'x':{'asset':'source.zip'}},'assets':[{'asset':'source.zip','bytes':8}]}))
            with self.assertRaisesRegex(ValueError,'missing'):
                recipe.catalog_plan(path,['graph/*','missing/*'],'core')

    def test_snapshot_manifest_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'evidence.txt';p.write_text('original')
            (root/'checksums.json').write_text(json.dumps({'evidence.txt':recipe.digest(p)}))
            self.assertEqual(recipe.verify_bundle(root),1)
            p.write_text('changed')
            with self.assertRaisesRegex(ValueError,'differs'):recipe.verify_bundle(root)

    def test_snapshot_manifest_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'bundle';root.mkdir();outside=Path(tmp)/'outside.txt';outside.write_text('x')
            (root/'checksums.json').write_text(json.dumps({'../outside.txt':recipe.digest(outside)}))
            with self.assertRaisesRegex(ValueError,'Unsafe'):recipe.verify_bundle(root)

    def test_payload_keeps_evidence_but_not_duplicate_bulk_or_old_wrong_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            keep=['medical/input/source.tsv','context/agriculture_selected_source_rows.parquet',
                'context/organisation_headcount_2025.parquet','education/primary_metric_cells.parquet',
                'education/supply_final_corrected.parquet','routes/nearest/school.parquet','routes_sites/nearest/school.parquet',
                'audit/lo_normative_comparison/pair_level_comparison.parquet','audit/sources/normative.txt',
                'audit/national_np_final/audit_run.json']
            drop=['education/primary/raw_book.xlsx','education/raw/lossy.csv','education/supply_final.parquet',
                'dependencies/graph/part.bin','source/stat.info_NP_2025.rar','routes/run.log',
                'audit/np_current_checked/audit_run.json','audit/national_np_final/screened_assignments.parquet']
            for name in keep+drop:
                p=work/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
            selected=recipe.payload_files(work)
            self.assertTrue(set(keep)<=set(selected))
            self.assertFalse(set(drop)&set(selected))

    def test_compact_mode_copies_inputs_but_recomputes_derived_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle';work=Path(tmp)/'new';bundle.mkdir();work.mkdir()
            paths=['context/census_reference.parquet','routes/nearest/school.parquet','model/units.parquet','figures/old.pdf']
            for name in paths:
                p=bundle/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
            (bundle/'checksums.json').write_text(json.dumps({n:recipe.digest(bundle/n) for n in paths}))
            recipe.compact_prepare(bundle,work)
            self.assertTrue((work/'routes/nearest/school.parquet').exists())
            self.assertFalse((work/'model/units.parquet').exists())
            self.assertFalse((work/'figures/old.pdf').exists())
            scope=json.loads((work/'compact_prepare.json').read_text())
            self.assertFalse(scope['new_federal_source_scan'])
            self.assertFalse(scope['new_road_routing'])

    def test_full_input_plan_omits_historical_sgrt_and_full_pair_matrices(self):
        planned=recipe.plan()
        self.assertEqual(planned['mode'],'full_primary_reproduction')
        self.assertFalse(planned['primary_population_modified'])
        patterns=recipe.PILOT_PATTERNS+recipe.HISTORICAL_PATTERNS
        self.assertFalse(any('candidate_travel_times_parts' in p for p in patterns))
        self.assertTrue(any('road_nodes' in p for p in patterns))
        self.assertTrue(any('graph_npz_parts' in p for p in patterns))
        self.assertEqual(recipe.PREFIX,'sgrt/mass20261024')

    def test_incomplete_result_does_not_destroy_previous_built_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);old=work/'built/previous.txt';old.parent.mkdir();old.write_text('keep')
            with self.assertRaisesRegex(ValueError,'incomplete scientific result'):
                recipe.package(work,recipe.TAG,'a'*40)
            self.assertEqual(old.read_text(),'keep')

    def test_audits_receive_their_actual_offer_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            for folder in ['routes','routes_sites']:
                path=work/folder/'nearest/school_general.parquet';path.parent.mkdir(parents=True);path.touch()
            with patch.object(recipe,'run') as mocked:recipe.analyses(work)
            audits=[list(call.args[1:]) for call in mocked.call_args_list if Path(call.args[0]).name=='audit.py']
            self.assertEqual(len(audits),2)
            self.assertIn(work/'medical-corrected/supply.parquet',audits[0])
            self.assertIn(work/'education/supply_final_corrected.parquet',audits[0])
            self.assertIn(work/'site_geometry/site_road_seeds.parquet',audits[1])


if __name__=='__main__':unittest.main()
