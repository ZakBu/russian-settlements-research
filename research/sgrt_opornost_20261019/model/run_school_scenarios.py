"""Run the scenario field on an independently inventoried first-grade provider block.

No fitting to documented edges. Institution count is not capacity.
The result illustrates dependence on assumptions and does not certify SGRTs.
"""
from pathlib import Path
import json
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
inputs = ROOT / 'model' / 'scenario_inputs_SV2025'
inputs.mkdir(exist_ok=False)
axis = pd.read_parquet(ROOT / 'data' / 'point_axis.parquet')
inventory = pd.read_csv(ROOT / 'data' / 'school_inventory_linked.csv')
block = inventory[inventory.source_id.eq('SV2025')].copy()
assert len(block) == 9 and block.id.notna().all()
assert block.service_level.eq('general_education_admission_2025_2026').all()
counts = block.groupby('id').size().rename('q_documented_schools').reset_index()
candidates = counts.merge(axis[['id', 'lat', 'lon', 'name']], on='id', validate='one_to_one').rename(columns={'id': 'entity_uid'})
origins = axis[axis.municipality_upper_2021.str.contains('нижнетурин', case=False, na=False)].copy()
assert len(origins) > 0
origins = origins.rename(columns={'id': 'entity_uid'})
origins[['entity_uid', 'lat', 'lon', 'name', 'population_2021', 'population_2010']].to_parquet(inputs / 'origins.parquet', index=False)
candidates.to_parquet(inputs / 'candidates.parquet', index=False)
(inputs / 'scope.json').write_text(json.dumps({
    'source_id': 'SV2025', 'source_function': 'first_grade_admission_2025_2026',
    'candidate_selection': 'all_9_schools_in_document_5_settlement_nodes',
    'origin_scope': '2021_population_cohort_Nizhneturinsky_label_not_2025_boundary_crosswalk',
    'mass_units': 'school_institution_count_not_capacity',
    'parameter_calibration': 'none_explicit_scenarios_beta1.5_2_3_d0_5_10_20_qref1_5',
    'target_links_used_as_input': False, 'number_of_origins': len(origins),
    'supply_point_location': 'settlement_point_not_school_street_address',
}, ensure_ascii=False, indent=2) + '\n')
command = [sys.executable, str(ROOT / 'model' / 'functional_fields.py'),
           '--origins', str(inputs / 'origins.parquet'),
           '--candidates', str(inputs / 'candidates.parquet'),
           '--q-columns', 'q_documented_schools',
           '--out', str(ROOT / 'model' / 'scenario_school_SV2025')]
subprocess.run(command, check=True)
