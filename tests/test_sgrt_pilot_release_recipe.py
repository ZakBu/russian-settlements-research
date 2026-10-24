"""Publication must fail on denominator drift, missing cases, or false dating."""
import argparse
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts/sgrt_pilot'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load('check_release_outputs')
recipe = load('reproduce_release')


def reference_metrics():
    rows = []
    for run, model, matches in [('medical_presence', 'functional', 40), ('medical_presence', 'nearest', 40),
                                ('medical_presence', 'population', 1), ('medical_count', 'functional', 9),
                                ('medical_count', 'nearest', 40), ('medical_count', 'population', 1)]:
        rows.append(dict(run=run, model=model, source_scenario='spatial_proxy', observation_year=2021,
                         service_order='broad_recorded_function_not_service_order', supply_transform='binary' if run == 'medical_presence' else 'object_count', decay_family='exponential', half_life_minutes=30., kernel_floor=.05,
                         resolved_external_origins=216, origins_in_model_frame=216,
                         origins_exactly_matching_any_normative_provider=matches,
                         origins_with_any_normative_provider_in_source_supply=53,
                         agreement_all_resolved_origins=matches/216,
                         source_provider_coverage_all_resolved_origins=53/216,
                         parameters_fitted_to_these_relations=False, preregistered_blind_holdout=False,
                         evidence='normative_attachment_not_observed_trip'))
    return pd.DataFrame(rows)


class ReleaseScientificRegressionTests(unittest.TestCase):
    def setUp(self):
        self.metrics = reference_metrics()
        self.summary = {'unique_external_pairs': 216, 'unique_external_origins': 216, 'parameters_fitted_or_selected': False}

    def test_same_numerators_on_different_evaluation_cohort_rejected(self):
        self.metrics.loc[0, 'resolved_external_origins'] = 215
        with self.assertRaisesRegex(ValueError, 'same 216'):
            checker.check_reference_metrics(self.metrics, self.summary)

    def test_bad_percentage_cannot_hide_behind_correct_count(self):
        self.metrics.loc[0, 'agreement_all_resolved_origins'] = .95
        with self.assertRaisesRegex(ValueError, 'percentage'):
            checker.check_reference_metrics(self.metrics, self.summary)

    def test_missing_count_model_cannot_be_published_as_full_comparison(self):
        with self.assertRaisesRegex(ValueError, 'Missing/duplicated'):
            checker.check_reference_metrics(self.metrics.iloc[:-1], self.summary)

    def test_duplicate_best_row_cannot_replace_other_model(self):
        self.metrics.iloc[-1] = self.metrics.iloc[0]
        with self.assertRaisesRegex(ValueError, 'Duplicated'):
            checker.check_reference_metrics(self.metrics, self.summary)

    def test_correct_counts_on_wrong_source_year_rejected(self):
        self.metrics.loc[0, 'observation_year'] = 2025
        with self.assertRaisesRegex(ValueError, 'source scenario/year'):
            checker.check_reference_metrics(self.metrics, self.summary)

    def test_normative_data_cannot_be_relabelled_observed_trips(self):
        self.metrics.loc[0, 'evidence'] = 'observed_patient_trip'
        with self.assertRaisesRegex(ValueError, 'evidence'):
            checker.check_reference_metrics(self.metrics, self.summary)

    def test_parameter_selection_invalidates_fixed_evaluation(self):
        self.summary['parameters_fitted_or_selected'] = True
        with self.assertRaisesRegex(ValueError, 'selected'):
            checker.check_reference_metrics(self.metrics, self.summary)

    def test_validation_recipe_reads_raw_source_before_comparing_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(workdir=Path(temporary), start_at='validation', stop_after='validation', catalog=ROOT/'data/catalog.json')
            with patch.object(recipe, 'run') as run:
                recipe.reproduce(args)
            scripts = [call.args[0] for call in run.call_args_list]
            self.assertLess(scripts.index('validate_medical_source.py'), scripts.index('compare_medical_attachments.py'))
            self.assertLess(scripts.index('independent_checks.py'), scripts.index('compare_medical_attachments.py'))

    def test_map_orchestration_keeps_planning_list_separate_from_osm(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            for case in checker.CASES:
                path = work/'outputs/model'/case/'scenario_outcomes.parquet'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()  # Modules are mocked: no fabricated scientific output is read.
            args = argparse.Namespace(workdir=work, start_at='maps', stop_after='maps', catalog=ROOT/'data/catalog.json')
            with patch.object(recipe, 'run') as run:
                recipe.reproduce(args)
            calls = [call.args for call in run.call_args_list if call.args[0] == 'visualize.py' and '--outcomes' in call.args]
            self.assertEqual(len(calls), 9)
            for args in calls:
                path = args[args.index('--outcomes')+1]
                label = args[args.index('--source-label')+1]
                if path.parent.name == 'official_udmurt_selected_plan':
                    self.assertIn('план 2026', label)
                    self.assertIn('не подтверждена', label)
                    self.assertNotIn('OSM', label)
                else:
                    self.assertIn('OSM', label)
                    self.assertIn('2021', label)


if __name__ == '__main__':
    unittest.main()
