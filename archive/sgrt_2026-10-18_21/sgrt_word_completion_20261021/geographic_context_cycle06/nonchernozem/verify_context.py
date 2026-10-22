"""Source-frame and stable-axis readback; independent stakeholder audit remains separate."""
from pathlib import Path
import pandas as pd,json,hashlib
H=Path(__file__).resolve().parent;R=H.parents[1];D=R/'data/source_controls_cycle05'
a=pd.read_parquet(D/'full_settlement_axis_cycle05_federal_children.parquet');o=pd.read_parquet(H/'settlement_historical_nonchernozem_context_1974.parquet');roster=pd.read_parquet(D/'latest2021_np_roster_complete_accounting.parquet');add=pd.read_parquet(D/'federal_np2021_axis_addendum.parquet')
primary_ids=set(roster.loc[roster.source_roster_status.eq('accepted_axis2021_native_code_population_match'),'id'])|set(add.id)
axis_observed=set(a.loc[a.source_record_id_2021.notna()&~a.axis_kind.eq('federal_territory_source_unit'),'id'])
assert primary_ids==axis_observed and len(primary_ids)==155746
assert o.id.equals(a.id) and o.region.equals(a.region) and len(o)==173862
mapping=json.loads((H/'finite_source29_to_axis_regions.json').read_text());admission=json.loads((R/'reviews/cycle06/nonchernozem_historical_source_visual_admission.json').read_text());assert set(x['axis_region_key'] for x in mapping)==set(admission['finite29_axis_keys']);assert len(mapping)==29
keys=set(admission['finite29_axis_keys'])|({'ненецкий'} if admission['nenets_extension_admitted'] else set())
expected={uid for uid,region in zip(a.id,a.region) if uid in primary_ids and region in keys}
actual=set(o.loc[o.nonchernozem_historical_regional_context_1974.fillna(False),'id']);assert expected==actual
assert not o.nonchernozem_historical_regional_context_1974.eq(False).any();assert o.loc[~o.id.isin(expected),'nonchernozem_historical_regional_context_1974'].isna().all()
assert not o.loc[o.region.isin(['москва','санкт петербург','севастополь','крым']),'nonchernozem_historical_regional_context_1974'].fillna(False).any()
r=dict(status='PASS',source_roster_native_ids=len(primary_ids),axis_order_and_region_preserved=True,primary29_exact_admitted_keys=True,positive_ids=len(actual),missing_positive_ids=0,unexpected_positive_ids=0,unknown_ids=int(o.nonchernozem_historical_regional_context_1974.isna().sum()),false_values=0,output_sha256=hashlib.sha256((H/'settlement_historical_nonchernozem_context_1974.parquet').read_bytes()).hexdigest(),independent_guardian_audit_separate=True)
(H/'verification.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
