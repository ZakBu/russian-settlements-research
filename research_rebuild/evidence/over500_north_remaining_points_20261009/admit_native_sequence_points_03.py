from pathlib import Path
import pandas as pd,json,hashlib,re,xlrd,ast,sys,gzip
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;N=R/'research_rebuild/evidence/over500_north_20261009';S=Path('/dev/shm/settlements-stage71-20261009');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();f=pd.read_parquet(S/'applied_state_observations.parquet').fillna('');b=f.set_index('source_record_id');sel=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');m=pd.read_parquet(sel).fillna('').set_index('source_record_id');ps=S/'applied_point_snapshot.parquet';p=pd.read_parquet(ps,columns=['target_source_record_id','latitude','longitude','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','own_locality_point','coordinate_admission_status']).fillna('').drop_duplicates('target_source_record_id').set_index('target_source_record_id').to_dict('index');pins={str(q):sha(q) for q in [S/'applied_state_observations.parquet',sel,ps]};books={};checks={};rawpar={};fn=ast.unparse(next(x for x in ast.parse((N/'build_packet.py').read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='check')).replace("actual = re.sub('ского$', 'ский', actual)","actual = re.sub('ского$', 'ский', actual); actual = re.sub('цкого$', 'цкий', actual)");exec(fn)
for folder,names in [(N,['accepted_point_use_delta.csv','supplemental_accepted_point_use_delta.csv','supplemental_accepted_point_use_delta_v2.csv','current_carrier_accepted_point_use_delta.csv','dated_subcounty_accepted_point_use_delta.csv','sosnovka_classifier_accepted_point_use_delta.csv','subcounty_anchor_accepted_point_use_delta.csv']),(O,['accepted_point_use_delta_01.csv','accepted_point_use_delta_02.csv'])]:
 for name in names:
  q=folder/name;pins[str(q)]=sha(q)
  for r in pd.read_csv(q).fillna('').to_dict('records'):p[r['target_source_record_id']]=r
old=f[f.source_record_id.isin(m.index)].copy();old['sheet']=old.source_record_id.map(m.source_sheet);old['row']=pd.to_numeric(old.source_record_id.map(m.source_row),errors='coerce');gmap={k:g.sort_values('row').to_dict('records') for k,g in old.groupby(['census_year','region_norm','source_file','sheet'])};by={}
for g in gmap.values():
 for i,z in enumerate(g):by[z['source_record_id']]=(g,i)
def context(sid):
 if sid not in by:return []
 g,i=by[sid];return [(j-i,g[j]['name_norm'],g[j]['source_record_id'],g[j]['row']) for j in range(max(0,i-2),min(len(g),i+3)) if j!=i]
remaining=pd.read_csv(O/'per_record_dispositions_01.csv');assigned=set(remaining.source_record_id);rows=[];edges=[];proof=[];review=[];blocked_names={'Кузнецы','Ушаково','Старомочалей'}
for z in f[f.source_record_id.isin(assigned)&(f.census_year==2010)].to_dict('records'):
 sid=z['source_record_id'];left=context(sid);hits=[]
 for r in old[(old.census_year==2002)&(old.region_norm==z['region_norm'])&(old.name_norm==z['name_norm'])].to_dict('records'):
  right=context(r['source_record_id']);pairs=[(x,y) for x in left for y in right if x[0]==y[0] and x[1]==y[1]]
  if len({x[0][1] for x in pairs})>=2:hits.append((r,pairs))
 if len(hits)!=1:continue
 r,pairs=hits[0];osid=r['source_record_id'];reason=[]
 if z['settlement_name'] in blocked_names:reason.append('ownpoint provider alternative or subtype/code binding requires separate review')
 if osid not in p:reason.append('paired primary2002 ownleaf lacks independently admitted ownpoint')
 allids=list(dict.fromkeys([sid,osid]+[a[0][2] for a in pairs]+[a[1][2] for a in pairs]));native=[check(i) for i in allids]
 if not all(a['literal_label_population_passed'] for a in native):reason.append('reopened original native target or neighbour fails')
 if not check(osid).get('actual_printed_county'):reason.append('no independently reopened primary2002 printed county')
 review.append({'source_record_id':sid,'paired_primary2002_ownleaf':osid,'matches':json.dumps(pairs,ensure_ascii=False),'disposition':'hold:'+','.join(reason) if reason else 'accepted_source_binding_point'})
 if reason:continue
 cp=p[osid];assert cp['coordinate_admission_status']=='reviewed_extension_rule_accepted';rule='Uniquely consistent same literal ownname and region across primary2002 and source2010, with at least2 distinct ownnamed physical neighbouring source records in identical signed local sequence positions; every target/neighbour literal label/count separately reopened in each raw source, primary2002 printed native county independently reopened. All same-name primary candidates tested; only this ownnative sequence matches. Independently admitted ownpoint of that primary leaf reused by explicit continuity; no count/quality/day-boundary assertion.'
 if sid not in p:
  row={k:cp[k] for k in ['latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind']};row.update(target_source_record_id=sid,coordinate_source_record_id=osid,coordinate_admission_status='reviewed_extension_rule_accepted',decision_status='checked_rule_accepted',admission_allowed=True,own_locality_point=True,recipient_point_assigned_to_child=False,source_sha256=check(sid)['source_sha256'],source_locator=f"{check(sid)['source_sheet']}:{check(sid)['source_row']}",source_bound_primary2002_counterpart=osid,admission_rule=rule,point_temporal_interpretation='Previously admitted own representative of source-bound primary leaf reused historically by explicit continuity inference; no exact censusday geometry or boundary equivalence.',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,native_population_quality_preserved=True);rows.append(row)
 g=f[f.root.isin([z['root'],r['root']])];yearcollision=g.census_year.duplicated().any();edgewhy=[]
 if z['type_norm']!=r['type_norm']:edgewhy.append('native typed roles differ; point_only')
 if yearcollision:edgewhy.append('existing graph has repeated sourceyear; point_only')
 if z['root']==r['root']:edgewhy.append('already_connected')
 if not edgewhy:edges.append({'from_source_record_id':sid,'to_source_record_id':osid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':rule+' Exact native typed roles also agree; union has no repeated sourceyear.','source_context_witness_file':str(O/'native_sequence_witnesses_03.json.gz'),'source_counts_changed':False,'boundary_comparability_asserted':False})
 proof.append({'source_record_id':sid,'primary2002_source_record_id':osid,'unique_original_source_sequence_matches':pairs,'all_reopened_target_and_neighbour_witnesses':native,'point_donor':cp,'typed_roles':{'2002':r['settlement_type'],'2010':z['settlement_type']},'identity_edge_disposition':edgewhy or ['accepted'],'all_name_rivals_primary2002':old[(old.census_year==2002)&(old.region_norm==z['region_norm'])&(old.name_norm==z['name_norm'])][['source_record_id','settlement_type','district_raw']].to_dict('records')})
pd.DataFrame(rows).to_csv(O/'accepted_point_use_delta_03.csv',index=False);pd.DataFrame(edges).to_csv(O/'accepted_identity_edges_03.csv',index=False);pd.DataFrame(review).to_csv(O/'native_sequence_reviews_03.csv',index=False)
with gzip.GzipFile(filename=str(O/'native_sequence_witnesses_03.json.gz'),mode='wb',mtime=0) as q:q.write(json.dumps(proof,ensure_ascii=False,default=str).encode())
(O/'manifest_03.json').write_text(json.dumps({'status':'frozen_accepted_native_sequence_bound_ownpoints_and_typed_identity_edges','points':len(rows),'identity_edges':len(edges),'sourcecounts_or_quality_modified':False,'input_pins':pins,'output_pins':{str(q):sha(q) for q in [O/'accepted_point_use_delta_03.csv',O/'accepted_identity_edges_03.csv',O/'native_sequence_reviews_03.csv',O/'native_sequence_witnesses_03.json.gz']}},ensure_ascii=False,indent=2)+'\n');print('points',len(rows),[b.loc[x['target_source_record_id'],'settlement_name'] for x in rows],'edges',len(edges))
