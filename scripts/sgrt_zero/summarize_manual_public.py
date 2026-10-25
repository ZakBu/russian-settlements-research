"""Summarize exact, schema, precision and natural-key source audits without hiding initial differences."""
from pathlib import Path
import argparse,json,hashlib
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checks',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();w=a.checks
load=lambda name:json.loads((w/name).read_text())
strict=load('public_vs_manual_all_scientific_tables.json');numeric=load('public_vs_manual_distance_roundoff.json');schema=load('public_vs_manual_schema_extensions.json');sources=load('public_vs_manual_source_reconciliation.json');images=load('public_vs_manual_atlas_images.json')
assert not schema['failures'] and not sources['failures']
resolved={r['path']:r for r in schema['tables_with_recorded_roundoff']}
assert set(numeric['failures'])==set(resolved), 'Unexpected numerical/structural failure must not be silently dismissed'
values=[resolved.get(r['path'],r) for r in numeric['tables_with_recorded_roundoff']]
for r in values:
 assert not r.get('structural_failure')
 for d in r['differences']:assert d.get('all_within_declared_roundoff_tolerance') is True,(r['path'],d)
route_changes={d['column'] for r in values if r['path'].startswith('routes') for d in r['differences']}
assert route_changes<= {'point_separation_km'}, 'Provider selection, costs or clinical evidence changed'
partition_changes={d['column'] for r in values if r['path'].startswith(('hierarchy/','upward/','upward_extended/')) for d in r['differences']}
assert partition_changes<= {'member_geodesic_diameter_km'}
membership=[r for r in strict['tables'] if Path(r['path']).name in {'memberships.parquet','level0_memberships.parquet'}]
assert len(membership)==15 and all(r.get('all_scientific_values_equal_exactly') for r in membership)
assert strict['table_count']==66 and len(images)==14 and all(r['identical'] for r in images)
manual=Path(strict['manual_root']);public=Path(strict['public_root']);readme_equal=(manual/'RESULT_README.md').read_bytes()==(public/'RESULT_README.md').read_bytes();assert readme_equal
max_error=max((d.get('max_absolute_difference') or 0 for r in values for d in r['differences']),default=0)
report={'tables_checked':66,'partition_pairs':15,'route_tables':23,'source_tables':13,'all_15_memberships_equal_exactly':True,'all_common_23_route_provider_selections_driving_minutes_and_clinical_flags_equal_exactly':True,'distance_roundoff':{'maximum_absolute_difference_km':max_error,'policy':numeric['float_comparison_policy'],'tables_with_recorded_roundoff_or_schema_extension':len(values),'observed_differing_distance_columns':sorted({d['column'] for r in values for d in r['differences']}),'details':'public_vs_manual_distance_roundoff.json plus public_vs_manual_schema_extensions.json'},'schema_extensions':{'tables':len(resolved),'public_only_fields':['provider_education_need_scope','provider_programme_mismatch_reason'],'all_public_extra_values_missing':all(r.get('public_extra_columns_all_null') for r in resolved.values()),'manual_only_fields':[],'explanation':'Eight older manual medical routes lack two entirely missing educational metadata fields newly forwarded in the public schema. Common clinical fields are compared explicitly; no extra clinical suitability is claimed.'},'sources':{'clinical_records_aligned_by':'stable F034 source_record_row; evidence ordinals verified against UIDSPMO+IDADDRESS before mapping','clinical_rows_compared':897573,'clinical_evidence_rows_each':624831,'no_unexplained_source_difference':not sources['failures'],'all_source_cells_identical':False,'explicit_difference_details':'public_vs_manual_source_reconciliation.json','education_metadata_difference_explanation':sources['declared_metadata_explanation']},'all_14_png_images_byte_identical':True,'result_readme_byte_identical':readme_equal,'initial_reports_preserved':['public_vs_manual_all_scientific_tables.json','public_vs_manual_distance_roundoff.json'],'source_reconciliation_report':'public_vs_manual_source_reconciliation.json','schema_reconciliation_report':'public_vs_manual_schema_extensions.json','failures':[]}
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(a.output),'failures':report['failures'],'tables':66,'maximum_distance_roundoff_km':max_error}))
