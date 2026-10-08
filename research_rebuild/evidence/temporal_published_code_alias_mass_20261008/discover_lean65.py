from pathlib import Path
AL=Path('/workspace/russian-settlements-research/research_rebuild/evidence/temporal_source_alias_reserve_20261008');OUT=Path(__file__).parent
import json,sys,re,collections,ast
import pandas as pd,duckdb
R=AL.parents[2];O=AL;B=AL.parent/'grounded_current_carrier_expansion_20261008';A=AL.parent/'main_axis_residual_application65_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
from build_long_table import UnionFind
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');P=A/'applied_point_snapshot.parquet';C=A/'applied_component_snapshot.csv.gz';F=A/'applied_remaining_primary.csv.gz';G=AL.parent/'temporal_after_new_current_points_20261008/resolved_candidate_geometry.parquet';cc=duckdb.connect();f=cc.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,population,is_additive_settlement_record,okato,oktmo from read_parquet(?)',[str(A/'applied_state_observations.parquet')]).fetchdf();pf=cc.execute('select target_source_record_id,latitude,longitude from read_parquet(?)',[str(P)]).fetchdf();gc=cc.execute('select * from read_parquet(?)',[str(G)]).fetchdf().set_index('source_record_id').to_dict('index');cc.close();rd=f.set_index('source_record_id').to_dict('index');del f;p=pf.set_index('target_source_record_id').to_dict('index');del pf;cs=pd.read_csv(C,keep_default_na=False).set_index('source_record_id').to_dict('index');remaining=set(pd.read_csv(F,usecols=['source_record_id']).source_record_id);uf=UnionFind(cs);mg=collections.defaultdict(list)
for i,z in cs.items():mg[z['root']].append(i)
for ids in mg.values():
 for i in ids[1:]:uf.union(ids[0],i)
mg=collections.defaultdict(list)
for i in cs:mg[uf.find(i)].append(i)
mg=dict(mg)
def coord(i):return float(p[i]['latitude']),float(p[i]['longitude'])
tree=ast.parse((B/'discover_closed_geometry.py').read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['nm','ty']],type_ignores=[]),'closed_names','exec'))
pins={str(q):sha(q) for q in [P,C,F,G,A/'applied_state_observations.parquet',A/'application_receipt.json']};event=set()
for q in [A/'lifecycle_round2_accepted_source_UID_credit_union.csv',AL.parent/'main_axis_residual_application63_20261008/lifecycle_round2_accepted_source_UID_credit_union.csv',AL.parent/'remaining_large_lifecycle_residual_20261008/accepted_direct_event_native_credit_union.csv']:
 if q.exists():event.update(pd.read_csv(q).source_record_id);pins[str(q)]=sha(q)
for n in ['direct_inclusion_transformation_path_native_credit_union.csv','formation_path_native_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','complete_publisher_partition_members.csv']:
 q=AL.parent/'working_full_chain_20261007'/n
 if q.exists():event.update(pd.read_csv(q).source_record_id);pins[str(q)]=sha(q)
# Preserve source-author grain: explicit statistical parts never become whole-NP identity through codes.
cc=duckdb.connect();caption=cc.execute('select source_record_id,source_name_raw from read_parquet(?)',[str(S)]).fetchdf().set_index('source_record_id').source_name_raw.to_dict();cc.close();pins[str(S)]=sha(S);source_grade={}
for dq,mq in [(AL.parent/'original_2002_population_control_residual_20261008/finalized_stage64_source100/accepted_source_observations_100_20col.csv',AL.parent/'original_2002_population_control_residual_20261008/finalized_stage64_source100/accepted_source_observation_metadata_100.csv'),(AL.parent/'residual_source_followup_20261008/finalized_Tver28_source_addon/accepted_Tver28_source_observations_20col.csv',AL.parent/'residual_source_followup_20261008/finalized_Tver28_source_addon/accepted_Tver28_source_metadata.csv')]:
 pins[str(dq)]=sha(dq);pins[str(mq)]=sha(mq)
 for zz in pd.read_csv(mq,keep_default_na=False).to_dict('records'):caption[zz['source_record_id']]=zz['source_name_raw'];source_grade[zz['source_record_id']]=zz.get('source_grade','secondary_compilation')
CODED=Path('/workspace/settlements-work/grounded_current_carrier_expansion_20261008/source_positive_coded_current_candidates.parquet');c=duckdb.connect();coded=c.execute('select target_source_record_id from read_parquet(?)',[str(CODED)]).fetchdf().astype(object).fillna('');RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');providerok=c.execute('select row_number()over() rn,okato_dadata from read_parquet(?)',[str(RAW)]).fetchdf().fillna('').set_index('rn').okato_dadata.to_dict();c.close();pins[str(RAW)]=sha(RAW)
# Actual65 already contains all accepted32+88+13+30 branches; no replay/duplicateaudits.
# Modernpublishedsourcecode is explicitly a modern named-object link, not asserted as native historical row code.
idx=collections.defaultdict(list);cpidx=collections.defaultdict(list)
for i,z in rd.items():
 if int(z['census_year'])==2021 and z['is_additive_settlement_record']:
  code=str(z['oktmo']).removesuffix('.0')
  if re.fullmatch(r'\d{11}',code):idx[(z['region_norm'],code)].append(i)
for z in coded.to_dict('records'):
 i=z['target_source_record_id'];code=str(providerok[int(i.rsplit(':',1)[1])]).removesuffix('.0')
 if code:cpidx[(rd[i]['region_norm'],code)].append(i)
pins[str(CODED)]=sha(CODED);rows=[];held=[];counts=collections.Counter();event.add('2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:3968')
for sid in sorted(remaining):
 row=rd[sid]
 if re.search(r'\b(?:часть|части|частью|всего|население)\b',normalize(caption.get(sid,row['settlement_name']))):counts['explicit statisticalpart/aggregate source caption excludes ordinarywholeNP identity']+=1;continue
 if int(row['census_year']) not in [2002,2010] or sid not in gc:continue
 gg=gc[sid];code=str(gg.get('source_own_code','')).removesuffix('.0');kind=''
 if gg['provider']=='RCSI' and re.fullmatch(r'\d{11}',code):carriers=idx[(row['region_norm'],code)];kind='modern_source_RCSI_own_OKTMO_to_actual_current_native_own_OKTMO'
 elif gg['provider']=='GeoKLADR2011' and re.fullmatch(r'\d{8,11}',code):carriers=cpidx[(row['region_norm'],code)];kind='dated_published_OKATO_named_leaf_to_independently_current_native_owncoded_FIAS_NP_classifier_crosswalk'
 else:counts['no typed positive moderncode namespace source']+=1;continue
 if len(carriers)!=1:counts['published code lacks unique proper current native carrier']+=1;continue
 cur=carriers[0]
 if cur not in p:counts['proper moderncoded counterpart has no acceptedownpoint']+=1;continue
 if uf.find(sid)==uf.find(cur):counts['identity already accepted in actual65']+=1;continue
 literal_names_equal=nm(row['settlement_name'])==nm(rd[cur]['settlement_name'])
 ids=mg[uf.find(sid)]+mg[uf.find(cur)];reason=[];g=(float(gg['latitude']),float(gg['longitude']));cg=coord(cur)
 if not gg['physical_NP_positive'] or nm(gg['raw_classifier_name'] if gg['provider']=='GeoKLADR2011' else gg['source_name'])!=nm(row['settlement_name']):reason.append('old named physicalsource body not literal nativeownNP')
 far_candidate=distance_km(g,cg)>5
 sourcecounty=county_key(str(gg.get('source_county','')));nativecounty=county_key(rd[cur]['district_raw'])
 historicalcounty=county_key(row['district_raw'])
 if far_candidate and (not historicalcounty or historicalcounty!=nativecounty):reason.append('far unaccepted candidate lacks positive printedhistoric/currentcounty agreement')
 if sourcecounty and nativecounty and sourcecounty!=nativecounty:reason.append('sourceownNP/currentcounty contradiction without datedtransferproof')
 if len({int(rd[i]['census_year']) for i in ids})!=len(ids):reason.append('actualsameyear componentrepetition')
 if any(i in event for i in ids):reason.append('publishednonordinary lifecycle scope')
 if any(i in p and distance_km(coord(i),cg)>5 for i in ids):reason.append('actualacceptedownpoint contradiction')
 rec={'from_source_record_id':sid,'to_source_record_id':cur,'from_year':int(row['census_year']),'from_name':row['settlement_name'],'to_name':rd[cur]['settlement_name'],'from_type':row['settlement_type'],'to_type':rd[cur]['settlement_type'],'from_county':row['district_raw'],'to_county':rd[cur]['district_raw'],'region':row['region_norm'],'from_population':row['population'],'to_population':rd[cur]['population'],'modern_code_namespace_route':kind,'published_modern_named_object_code':code,'historical_native_code_asserted':False,'sourcebody_native_old_name':gg['source_name'],'sourcebody_type':gg['source_type'],'sourcebody_county':gg['source_county'],'sourcebody_file':gg['source_file'],'sourcebody_locator':gg['source_locator'],'sourcebody_kind':gg['source_kind'],'oldsource_coordinate_distance_to_current_km':distance_km(g,cg),'component_source_ids_json':json.dumps(ids),'candidate_geometry_only_nohistoricalmeasurement':True,'code_provider_identifier_transfer_asserted':False,'literal_native_names_equal':literal_names_equal,'old_far_unaccepted_geometry_not_hard_contradiction':far_candidate,'positive_printed_historical_county':historicalcounty}
 if reason:held.append({**rec,'held_reason':'; '.join(reason)});counts.update(set(reason))
 else:rows.append(rec);counts[kind+': candidateonly sourcepositive alias']+=1
for n,x,cols in [('candidate_identity_pairs.csv.gz',rows,['from_source_record_id']),('held_code_alias_routes.csv.gz',held,['from_source_record_id','held_reason'])]:pd.DataFrame(x,columns=None if x else cols).to_csv(OUT/n,index=False,compression={'method':'gzip','mtime':0})
r={'baseline_stage':65,'actual65_snapshot_source_point_component_rows_hydrated':True,'accepted_edges':0,'accepted_points':0,'candidate_pairs':len(rows),'held_pairs':len(held),'old_candidate_population_by_year':{str(y):sum(float(z['from_population']) for z in rows if z['from_year']==y) for y in [2002,2010]},'sourcepublished_code_is_modern_object_code_not_native_historical_code':True,'no_State_load':True,'outcomes':dict(counts),'input_pins':pins,'output_pins':{q.name:sha(q) for q in OUT.glob('*.csv.gz')}};(OUT/'candidate_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
