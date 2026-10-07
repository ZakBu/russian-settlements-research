"""Apply the authorized frozen18-row native2002 context batch on explicit stage19."""
import sys,json,collections
from pathlib import Path
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');E=ROOT/'research_rebuild/evidence';OUT=Path(__file__).parent;CAND=E/'mass_residual_native_context_20261007'
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key

def main():
 state=load(stage=19)
 stage19=E/'current_unpointed_own_wiki_mass_application_20261007/accepted_point_use_delta.csv'
 if stage19 not in state.inputs:raise ValueError('Explicit stage19 loader not ready')
 before=state.metrics();receipt=json.loads((CAND/'receipt.json').read_text())
 for path,digest in receipt['inputs'].items():
  if sha(Path(path))!=digest:raise ValueError('Frozen candidate input changed: '+path)
 for name,digest in receipt['outputs'].items():
  if sha(CAND/name)!=digest:raise ValueError('Frozen candidate output changed: '+name)
 for rel,digest in receipt['native_source_hashes'].items():
  if sha(Path('/workspace/settlements-raw')/rel)!=digest:raise ValueError('Native workbook changed: '+rel)
 candidates=pd.read_csv(CAND/'candidates.csv',keep_default_na=False)
 if len(candidates)!=18 or candidates.from_source_record_id.duplicated().any():raise ValueError('Frozen authorized18 rows differ')
 # Stage19 adds points only, so the frozen full-universe uniqueness/context evaluation remains valid.
 metrics=state.metrics();edges=[];points=[];holds=[];retained=[]
 by_root=collections.defaultdict(list)
 for sid in state.obs.source_record_id:by_root[state.uf.find(sid)].append(sid)
 input_hashes={str(p):sha(p) for p in state.inputs};output_ledger=OUT/'accepted_point_use_delta.csv'
 for r in candidates.to_dict('records'):
  aid,bid=r['from_source_record_id'],r['to_source_record_id'];a,b=state.by_id.loc[aid],state.by_id.loc[bid];ra,rb=state.uf.find(aid),state.uf.find(bid)
  if ra==rb:holds.append({'source_record_id':aid,'reason':'already_connected_no_new_gain'});continue
  if state.years[ra]&state.years[rb] or state.years[ra]|state.years[rb]!={2002,2010,2021}:raise ValueError('Candidate no longer forms exclusive three-census chain')
  if int(a.census_year)!=2002 or int(b.census_year)!=2021 or any(normalize(a[k])!=normalize(b[k]) for k in ('name_norm','type_norm','region_norm')):raise ValueError('Native endpoints changed')
  if county_key(b.district_raw)!=r['inferred_current_county']:raise ValueError('Current county mismatch')
  for side in ('lower','upper'):
   oldid,curid=r[side+'_2002_anchor'],r[side+'_2021_anchor'];old,cur=state.by_id.loc[oldid],state.by_id.loc[curid]
   if state.uf.find(oldid)!=state.uf.find(curid) or county_key(cur.district_raw)!=r['inferred_current_county'] or old.source_file!=a.source_file or normalize(old.district_raw)!=normalize(a.district_raw):raise ValueError('Frozen anchor disagreement')
  donor=state.point_rows[bid]
  if donor.get('coordinate_source_record_id')!=bid:raise ValueError('Current point no longer own-bound')
  members=by_root[ra]+by_root[rb]
  for sid in members:
   oldpoint=state.point_rows.get(sid)
   if oldpoint and distance_km((oldpoint['latitude'],oldpoint['longitude']),(donor['latitude'],donor['longitude']))>5:raise ValueError('Existing component point conflict')
   if sid in state.conflicting_point_targets:raise ValueError('Unresolved accepted point alternatives')
  edge={**r,'from_year':2002,'to_year':2021,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'native_2002_printed_subdivision_two_sided_accepted_anchor_context_v1','current_county_printed_in_2002_asserted':False,'population_boundary_comparability_asserted':False,'review_basis':'authorized_bounded18_with_fixed15_plus_top5_physical_source_checks'}
  edges.append(edge);state.union(aid,bid)
  for sid in members:
   if sid in state.point_rows:
    retained.append({'source_record_id':sid,'action':'existing_accepted_point_preserved','point_ledger_path':state.point_rows[sid]['point_ledger_path']});continue
   ledger=Path(donor['point_ledger_path'])
   point={k:v for k,v in donor.items() if k.startswith('point_origin_')}
   point.update(target_source_record_id=sid,target_year=int(state.by_id.loc[sid,'census_year']),latitude=donor['latitude'],longitude=donor['longitude'],coordinate_source_record_id=bid,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_origin_ledger=str(ledger),coordinate_origin_ledger_sha256=sha(ledger),coordinate_origin_ledger_locator='target_source_record_id='+bid,coordinate_use_inference='representative_current_point_continuity_over_native_source_context',donor_point_origin_kind=donor.get('point_origin_kind',''),admission_rule='representative_point_continuity_over_native2002_context_identity',direct_historical_coordinate_measurement=False,native_code_binding_asserted=False,boundary_comparability_asserted=False,historical_source_file=r['source_file'],historical_source_sha256=r['source_sha256'],historical_source_sheet=r['source_sheet'],historical_source_row=r['source_row'],historical_source_name_raw=r['source_name_raw'],historical_printed_district=r['printed_2002_district'],historical_printed_municipality=r['printed_2002_municipality'],historical_lower_anchor=r['lower_2002_anchor'],historical_upper_anchor=r['upper_2002_anchor'],candidate_evidence_path=str(CAND/'candidates.csv'),candidate_evidence_sha256=sha(CAND/'candidates.csv'),point_ledger_path=str(output_ledger))
   points.append(point);state.point_rows[sid]=point
 pd.DataFrame(edges).to_csv(OUT/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(output_ledger,index=False);pd.DataFrame(retained).to_csv(OUT/'preserved_existing_point_uses.csv',index=False);pd.DataFrame(holds,columns=['source_record_id','reason']).to_csv(OUT/'held_candidates.csv',index=False)
 after=state.metrics();app={'status':'applied_authorized_bounded_native2002_source_context_rule','baseline_stage':19,'result_stage_proposed':20,'accepted_identity_edges':len(edges),'new_point_uses':len(points),'preserved_existing_point_uses':len(retained),'holds':holds,'before':before,'after':after,'full3_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'covered_rows_gain':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'inputs':input_hashes,'frozen_candidate_receipt_sha256':sha(CAND/'receipt.json'),'outputs':{p.name:sha(p) for p in OUT.glob('*.csv')},'population_values_modified':False,'current_county_printed_in_2002_asserted':False,'historical_representative_point_continuity_asserted':True,'historical_coordinate_measurement_asserted':False,'boundary_comparability_asserted':False}
 (OUT/'application_receipt.json').write_text(json.dumps(app,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:app[k] for k in ['accepted_identity_edges','new_point_uses','preserved_existing_point_uses','full3_population_gain','covered_rows_gain']},ensure_ascii=False))
if __name__=='__main__':main()
