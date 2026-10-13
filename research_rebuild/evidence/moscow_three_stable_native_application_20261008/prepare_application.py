from pathlib import Path
import sys,json,hashlib,math
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent
sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km
s=load(25);before=s.metrics();pins={str(p):sha(p) for p in s.inputs}
a='2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:';b='2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:';c='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'
cases=[('Ильинское',961,8862,65584,'Домодедовский район','Городской округ Домодедово',8860,8863),('Зеленый',3822,11487,68492,'Ногинский район','Богородский городской округ',11483,11488),('Рождествено',1935,9795,66986,'Истринский район','Городской округ Истра',9794,9797)]
raws={2002:Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls'),2010:Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls')}
frames={2002:pd.read_excel(raws[2002],sheet_name='Sheet1',header=None),2010:pd.read_excel(raws[2010],sheet_name='Data Sheet',header=None)}
for p in raws.values():pins[str(p)]=sha(p)
edges=[];points=[];checks=[];witness=[];affected=[]
for name,r02,r10,r21,oldcounty,newcounty,left,right in cases:
 ids=[a+str(r02),b+str(r10),c+str(r21)];affected+=ids;old02,old10,cur=[s.by_id.loc[x] for x in ids];assert old02.district_raw==oldcounty and cur.district_raw==newcounty
 assert old02.type_norm==old10.type_norm==cur.type_norm
 assert old02.name_norm==old10.name_norm==cur.name_norm
 # Two flanking accepted source rows establish historical and modern county context.
 anchorlist=[]
 for row in [left,right]:
  sid=b+str(row);root=s.uf.find(sid);g=s.obs[s.obs.root.eq(root)]; assert s.years[root]=={2002,2010,2021}
  assert g[g.census_year.eq(2002)].district_raw.iloc[0]==oldcounty
  assert g[g.census_year.eq(2021)].district_raw.iloc[0]==newcounty
  anchorlist.append({'source_record_id':sid,'name':s.by_id.loc[sid].settlement_name,'component_source_ids':g.source_record_id.tolist(),'old_county':oldcounty,'current_county':newcounty})
 for year,row,sid in [(2002,r02,ids[0]),(2010,r10,ids[1])]:
  raw=frames[year].iloc[row-1];label=str(raw[1 if year==2002 else 3]);pop=float(raw[2 if year==2002 else 4]);obs=s.by_id.loc[sid];assert pop==float(obs.population)
  assert name in label
  witness.append({'source_record_id':sid,'year':year,'raw_file':str(raws[year]),'raw_sha256':pins[str(raws[year])],'sheet':'Sheet1' if year==2002 else 'Data Sheet','row_1based':row,'name_cell':'B' if year==2002 else 'D','population_cell':'C' if year==2002 else 'E','printed_label':label,'native_population':pop,'population_value_quality_unchanged':obs.population_value_quality})
 currentpoint=s.point_rows[ids[2]];g=s.obs[s.obs.root.isin({s.uf.find(x) for x in ids})];assert not(set(g.source_record_id)&s.conflicting_point_targets)
 maxdist=max([distance_km((currentpoint['latitude'],currentpoint['longitude']),(s.point_rows[x]['latitude'],s.point_rows[x]['longitude'])) for x in g.source_record_id if x in s.point_rows] or [0]);assert maxdist<=5
 # Identity only; no equal boundaries or comparable population scope over time asserted.
 for sid in ids[:2]:
  if s.uf.find(sid)!=s.uf.find(ids[2]):
   edges.append({'from_source_record_id':sid,'to_source_record_id':ids[2],'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'Exact own settlement name and printed type; explicit 2002 county; two-sided accepted 2010 source county context; unique current own county/type/name and admitted physical point','native_2002_printed_code_asserted':False,'boundary_comparability_asserted':False,'source_context_witness_file':str(O/'native_binding_checks.csv')})
  if sid not in s.point_rows:
   point={k:v for k,v in currentpoint.items() if k!='point_ledger_path'};point.update(target_source_record_id=sid,coordinate_admission_status='reviewed_extension_rule_accepted',admission_allowed=True,admission_rule='Own accepted modern locality point retrospectively reused after native whole-place name/type/county continuity proof',point_temporal_interpretation='Modern own locality representative; no measured census-date coordinate claim',boundary_comparability_asserted=False,native_2002_printed_code_asserted=False,own_current_source_record_id=ids[2]);points.append(point)
 checks.append({'name':name,'source_ids_json':json.dumps(ids),'population_2002':float(old02.population),'population_2010':float(old10.population),'population_2021':float(cur.population),'source_type':cur.settlement_type,'old_county':oldcounty,'current_county':newcounty,'current_own_oktmo':cur.oktmo,'current_own_okato':cur.okato,'left_right_source_anchor_json':json.dumps(anchorlist,ensure_ascii=False),'component_max_existing_point_distance_km':maxdist,'active_component_point_conflicts':0,'all_unique_census_years_after_merge':True,'population_and_quality_unchanged':True,'same_name_different_type_or_county_excluded':True,'modern_boundary_comparability_asserted':False})
pd.DataFrame(edges).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(checks).to_csv(O/'native_binding_checks.csv',index=False);pd.DataFrame(witness).to_csv(O/'native_actual_source_row_witnesses.csv',index=False)
# Pin raw origins and the exact accepted ledgers from which points are reused.
for name,r02,r10,r21,*_ in cases:
 p=s.point_rows[c+str(r21)]
 for k in ['point_origin_file','point_ledger_path']:
  path=Path(p[k]);pins[str(path)]=sha(path)
# Frozen mixed baseline sidecars: secondary, complete partition, named merger source-ID unions.
report=R/'research_rebuild/evidence/working_full_chain_20261007';receipt=json.loads((report/'coverage_receipt.json').read_text());assert receipt['working_stage']==25
mixedextras=set()
for fn in ['qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_publisher_partition_members.csv']:
 p=report/fn;pins[str(p)]=sha(p);mixedextras.update(pd.read_csv(p,dtype=str).source_record_id)
def full3_ids():
 ids=set()
 for _,g in s.obs.groupby('root',sort=False):
  if set(g.census_year)=={2002,2010,2021} and g.population.notna().all() and all(x in s.point_rows for x in g.source_record_id):ids.update(g.source_record_id)
 return ids
pre_ids=full3_ids()|mixedextras
s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();post_ids=full3_ids()|mixedextras
net=s.obs[s.obs.source_record_id.isin(post_ids-pre_ids)].copy();net.to_csv(O/'actual_unique_selected_source_id_net_delta.csv',index=False)
assert set(net.source_record_id)==set(affected)-mixedextras
expected={2002:11349,2010:11611,2021:9681};actual={int(y):int(g.population.sum()) for y,g in net.groupby('census_year')};assert actual==expected,(actual,expected)
for row in checks:
 for sid in json.loads(row['source_ids_json']):assert s.years[s.uf.find(sid)]=={2002,2010,2021} and sid in s.point_rows
pins[str(report/'coverage_receipt.json')]=sha(report/'coverage_receipt.json');(O/'source_manifest.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2))
(O/'README.md').write_text('Three stable Moscow Oblast whole-locality identities, checked against stage 25.\n\nFive identity edges and five historical point uses complete three actual native census trajectories. Exact raw labels and populations are reread from source workbooks; protected 2010 counts and quality are unchanged. Printed type and historical county distinguish namesakes. Two-sided accepted source anchors resolve the unlabeled 2010 county. Own modern accepted locality points are reused retrospectively; no historical boundary harmonization or coordinate precision is invented. All active component points are coherent within 5 km.\n\nActual unique new mixed credit: 2002 11,349; 2010 11,611; 2021 9,681. Ordinary 2021 gain is 14,590; current Ilinskoe 4,909 was already qualified-credit covered. Ordinary and mixed gains must not be added together. Application is prepared; root integration remains pending. No loader, report, Git, source or existing accepted packet was edited.\n')
result={'status':'prepared_reviewed_application_root_integration_pending','baseline_working_stage':25,'identity_edges':len(edges),'historical_point_uses':len(points),'completed_native_trajectories':3,'ordinary_before':before,'ordinary_after':after,'ordinary_population_delta':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'actual_unique_mixed_selected_population_delta':actual,'actual_unique_mixed_selected_rows_delta':len(net),'protected_population_values_and_quality_preserved':True,'active_point_conflicts':0,'all_component_points_within_5km':True,'loader_report_git_mutated':False,'input_pin_manifest_sha256':sha(O/'source_manifest.json'),'output_sha256':{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name not in ['application_receipt.json']}}
(O/'application_receipt.json.tmp').write_text(json.dumps(result,ensure_ascii=False,indent=2));(O/'application_receipt.json.tmp').replace(O/'application_receipt.json');print(json.dumps({'edges':len(edges),'point_uses':len(points),'actual':actual,'ordinary_delta':result['ordinary_population_delta']},ensure_ascii=False))
