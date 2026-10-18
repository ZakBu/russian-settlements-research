#!/usr/bin/env python3
"""Read exact local primary cells for addressed diagnostic sample; do not impute dashes."""
from pathlib import Path
import pandas as pd,xlrd,re,json,hashlib
O=Path(__file__).resolve().parent;R=O.parents[1]/'repo';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
s=pd.read_csv(O/'sample_locator_checks.csv',keep_default_na=False);a=pd.read_csv(O/'diagnostic_sample120.csv',keep_default_na=False).set_index('entity_uid');rows=[]
for _,r in s[s.local_found.eq(True)].iterrows():
 if not r.local_path.endswith('.xls'):continue
 m=re.fullmatch(r'(.+):row(\d+):population_column_zero_based(\d+)',r.locator)
 if not m:continue
 sheet,row,col=m.groups();sh=xlrd.open_workbook(r.local_path).sheet_by_name(sheet);v=sh.cell_value(int(row)-1,int(col));caption=sh.cell_value(int(row)-1,0);expected=float(a.loc[r.entity_uid,'population_'+str(r.year)]);numeric=isinstance(v,(int,float));rows.append({'entity_uid':r.entity_uid,'year':r.year,'source_sha256':sha(r.local_path),'locator':r.locator,'raw_caption':caption,'selected_name':a.loc[r.entity_uid,'settlement_name_'+str(r.year)],'raw_population_cell':v,'selected_population':expected,'literal_numeric_population_matches':numeric and v==expected,'name_substring_matches':a.loc[r.entity_uid,'settlement_name_'+str(r.year)].casefold() in caption.casefold(),'identity_and_territory_equivalence_verified':False})
pd.DataFrame(rows).to_csv(O/'primary_literal_sample_readback.csv',index=False)
# Independent direct numeric reading of an available regional aggregate; no inference of record coverage.
p=R/'research_rebuild/evidence/next67_primary_source_routes/perm_2010_original_archived.xls';sh=xlrd.open_workbook(p).sheet_by_name('01-04');total=sh.cell_value(6,1);reg=pd.read_csv(O/'regional_panel_sums.csv').set_index('effective_region_norm_2002');ps=reg.loc['пермский','pop2010']
pd.DataFrame([{'region':'пермский','year':2010,'panel_sum':ps,'official_literal_region_total':total,'difference':ps-total,'population_share_against_published_total':ps/total,'same_year_geographic_region':True,'historical_boundary_comparability':'UNKNOWN','row_roster_reconciled':False,'record_coverage_share':'UNKNOWN','source_locator':'01-04;Excel row7;column_zero_based1','source_sha256':sha(p),'status':'direct_local_aggregate_readback_not_external_replication'}]).to_csv(O/'available_control_sum_check.csv',index=False)
(O/'primary_readback_receipt.json').write_text(json.dumps({'script_sha256':sha(__file__),'n':len(rows),'all_numeric_matches':all(r['literal_numeric_population_matches'] for r in rows),'all_name_substring_matches':all(r['name_substring_matches'] for r in rows),'permutation_not_attempted':True,'verified_cells_do_not_verify_boundary_continuity':True},indent=2))
print(len(rows),total,ps,ps/total)
