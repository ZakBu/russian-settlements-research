"""Repeat the new analyses using preserved inputs, then independent checks.

Network acquisition is intentionally separate, documented in README.md. This
script neither silently replaces unavailable inputs nor assigns treatment dates.
"""
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
scripts=[
    'outcomes/selection.py','outcomes/area_analysis.py','outcomes/area_sensitivity.py',
    'outcomes/recent_demography.py','outcomes/urban_remainder.py','outcomes/combined_outcomes.py',
    'history/analyze_wb_historical_profile.py','history/analyze_derived_ozon.py',
    'history/analyze_wb_profile_contexts.py','history/audit_wb_geography_independently.py',
    'audit_scope.py','analyze_national_context.py','render_figures.py',
    'review/independent_csv_check.py','review/independent_new_outcomes.py','review/independent_spatial_check.py',
    'review/independent_wb_context_check.py',
    'review/independent_scope_check.py',
]
for relative in scripts:
    print('Recalculating',relative,flush=True)
    subprocess.run([sys.executable,str(HERE/relative)],cwd=ROOT,check=True)
print('New descriptive analyses and independent arithmetic checks completed. No causal effect estimated.')
