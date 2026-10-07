"""Candidate-only exact normalized name/region + mutual unique accepted point within 5km."""
import sys,json,re,unicodedata,itertools
from pathlib import Path
from collections import Counter,defaultdict
import pandas as pd
import pyarrow.parquet as pq
ROOT=Path('/workspace/russian-settlements-research')
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,E
from current_chain_state_20261007 import distance_km,sha
from measure_event_aware_path_union_20261005 import SELECTED
OUT=Path(__file__).resolve().parent
EVENT_ROWS=E/'event_aware_path_union_20261005/accepted_event_path_selected_rows.csv'
EVENT_CODES=Path('/workspace/settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json')
def norm(v):
 if v is None or pd.isna(v):return ''
 v=unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е')
 return ' '.join(''.join(' ' if unicodedata.category(c).startswith('P') else c for c in v).split())
def main():
 s=load(); before=s.metrics(); inputs={str(p):sha(p) for p in s.inputs};inputs[str(ROOT/'research_rebuild/mass_linkage/working_state_20261007.py')]=sha(ROOT/'research_rebuild/mass_linkage/working_state_20261007.py')
 meta=pq.read_table(SELECTED,columns=['source_record_id','entity_grain_status','source_sheet','source_row','source_name_raw']).to_pandas().set_index('source_record_id')
 obs=s.obs.join(meta,on='source_record_id');obs['n']=obs.settlement_name.map(norm);obs['r']=obs.region_norm.map(norm);by=obs.set_index('source_record_id',drop=False)
 event_ids=set(pd.read_csv(EVENT_ROWS,usecols=['source_record_id'],dtype=str).source_record_id);codes=set()
 for r in json.loads(EVENT_CODES.read_text()):
  for k in ('from_settlement_id_legacy_candidate','to_settlement_id_legacy_candidate'):
   v=str(r.get(k) or '')
   if v.startswith(('RU-OKTMO-','RU-OKATO-')):codes.add(norm(v.rsplit('-',1)[-1]))
 inputs.update({str(p):sha(p) for p in [EVENT_ROWS,EVENT_CODES]})
 def rowholds(x):
  r=by.loc[x];h=[]
  if not bool(r.is_additive_settlement_record) or re.search(r'часть|\b(?:район|муниципальн\w*|городское население|сельское население|итого|всего)\b',norm(r.settlement_name)) or re.search('aggregate|municipal|parent|unresolved|control_total',str(r.entity_grain_status),re.I):h.append('nonwhole_or_admin_grain')
  if r.r in ['москва','санкт петербург','севастополь','крым']:h.append('out_of_scope_region')
  if x in event_ids or any(norm(r[k]) in codes for k in ['oktmo','okato']):h.append('known_event_member')
  if x in s.conflicting_point_targets:h.append('conflicting_accepted_point_alternatives')
  return h
 members=defaultdict(list)
 for sid in by.index:members[s.uf.find(sid)].append(sid)
 collisions=Counter((int(by.loc[x,'census_year']),p['latitude'],p['longitude']) for x,p in s.point_rows.items())
 original=set(s.point_rows);pointed=obs[obs.source_record_id.isin(original)&obs.n.ne('')]
 groups={(n,r):g for (n,r),g in pointed.groupby(['n','r'],sort=True)}
 pairs=[];outcomes=Counter();holds=[]
 for (n,r),g in groups.items():
  ys={int(y):list(d.source_record_id) for y,d in g.groupby('census_year')}
  for ya,yb in itertools.combinations(sorted(ys),2):
   near=[];degree=Counter()
   for a,b in itertools.product(ys[ya],ys[yb]):
    ap,bp=s.point_rows[a],s.point_rows[b];dist=distance_km((ap['latitude'],ap['longitude']),(bp['latitude'],bp['longitude']))
    if dist<=5:near.append((a,b,dist));degree[a]+=1;degree[b]+=1
   for a,b,dist in near:
    if s.uf.find(a)==s.uf.find(b):outcomes['already_connected']+=1;continue
    if degree[a]!=1 or degree[b]!=1:
     holds.append({'from_source_record_id':a,'to_source_record_id':b,'reason':'not_mutual_unique_nearby_same_name_same_region','distance_km':dist});outcomes['not_mutual_unique_nearby_same_name_same_region']+=1;continue
    pairs.append((a,b,dist))
 pairs.sort(key=lambda p:(-float(by.loc[p[0],'population'] or 0)-float(by.loc[p[1],'population'] or 0),p[0],p[1]))
 edges=[];points=[];seen=set();ledgerhash={}
 for a,b,dist in pairs:
  ra,rb=s.uf.find(a),s.uf.find(b)
  if ra==rb:outcomes['already_connected_after_simulation']+=1;continue
  if frozenset([ra,rb]) in seen:outcomes['duplicate_component_pair']+=1;continue
  seen.add(frozenset([ra,rb]));m=members[ra]+members[rb];reasons=[]
  if s.years[ra]&s.years[rb]:reasons.append('repeated_year_component')
  accepted=[x for x in m if x in original];donor=max(accepted,key=lambda x:int(by.loc[x,'census_year']));dp=s.point_rows[donor];coord=(dp['latitude'],dp['longitude'])
  for x in m:
   reasons.extend(rowholds(x));r=by.loc[x];p=s.point_rows.get(x)
   if p and collisions[(int(r.census_year),p['latitude'],p['longitude'])]>1:reasons.append('shared_same_year_accepted_point')
   if x not in s.point_rows and collisions[(int(r.census_year),*coord)]>0:reasons.append('proposed_transfer_same_year_point_collision')
   if pd.notna(r.latitude) and pd.notna(r.longitude) and (r.latitude,r.longitude)!=(0,0) and -90<=r.latitude<=90 and -180<=r.longitude<=180 and distance_km(coord,(r.latitude,r.longitude))>5:reasons.append('native_source_coordinate_contradiction')
  for x,z in itertools.combinations(accepted,2):
   xp,zp=s.point_rows[x],s.point_rows[z]
   if distance_km((xp['latitude'],xp['longitude']),(zp['latitude'],zp['longitude']))>5:reasons.append('component_accepted_points_over_5km')
  if reasons:holds.append({'from_source_record_id':a,'to_source_record_id':b,'reason':';'.join(sorted(set(reasons))),'distance_km':dist});outcomes.update(set(reasons));continue
  ar,br=by.loc[a],by.loc[b];ap,bp=s.point_rows[a],s.point_rows[b]
  same_origin=str(ap.get('coordinate_source_record_id',''))==str(bp.get('coordinate_source_record_id','')) and str(ap.get('coordinate_source_record_id',''))!=''
  edge={'from_source_record_id':a,'to_source_record_id':b,'from_year':int(ar.census_year),'to_year':int(br.census_year),'relation':'same_place','decision_status':'candidate_pending_independent_review','name_norm':ar.n,'region_norm':ar.r,'normalization_rule':'NFKC; casefold; ё→е; Unicode punctuation including hyphen→space; whitespace collapse','distance_km':dist,'both_endpoint_points_already_accepted':True,'mutual_unique_within_5km_same_name_region_year_pair':True,'possible_type_change':norm(ar.settlement_type)!=norm(br.settlement_type),'county_disagreement':norm(ar.district_raw)!=norm(br.district_raw),'population_comparability_asserted':False,'boundary_comparability_asserted':False,'provider_identifier_binding_asserted':False,'independent_point_corroboration_asserted':False,'copied_same_coordinate_donor':same_origin and (ap['latitude'],ap['longitude'])==(bp['latitude'],bp['longitude']),'admission_rule':'exact_normalized_name_same_region_mutual_unique_already_accepted_points_within_5km_v1','point_donor_source_record_id':donor,'from_previous_component_years':','.join(map(str,sorted(s.years[ra]))),'to_previous_component_years':','.join(map(str,sorted(s.years[rb])))}
  for side,x,p in [('from',a,ap),('to',b,bp)]:
   r=by.loc[x]
   for field in ['settlement_name','settlement_type','district_raw','population','source_file','source_path','source_sha256','source_locator','source_sheet','source_row','source_name_raw','entity_grain_status']:edge[side+'_'+field]=r[field]
   edge[side+'_normalization_proof']=norm(r.settlement_name)
   for field in ['latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','source_locator','source_sha256','point_ledger_path']:edge[side+'_point_'+field]=p.get(field,'')
   ledger=Path(p['point_ledger_path']);ledgerhash.setdefault(str(ledger),sha(ledger));edge[side+'_point_ledger_sha256']=ledgerhash[str(ledger)]
  edges.append(edge);s.union(a,b);members[s.uf.find(a)]=m
  for x in m:
   if x in s.point_rows:continue
   p={'target_source_record_id':x,'target_year':int(by.loc[x,'census_year']),'latitude':coord[0],'longitude':coord[1],'coordinate_source_record_id':donor,'coordinate_admission_status':'candidate_pending_independent_review','coordinate_origin_ledger':dp['point_ledger_path'],'coordinate_origin_ledger_sha256':ledgerhash[dp['point_ledger_path']],'coordinate_origin_ledger_locator':'target_source_record_id='+donor,'direct_historical_coordinate_measurement':False,'native_code_binding_asserted':False,'boundary_comparability_asserted':False,'admission_rule':'representative_point_continuity_over_proposed_5km_identity'}
   points.append(p);s.point_rows[x]=dict(p,point_ledger_path=str(OUT/'candidate_point_use_delta.csv'));collisions[(int(by.loc[x,'census_year']),*coord)]+=1
 after=s.metrics();pd.DataFrame(edges).to_csv(OUT/'candidate_identity_edge_delta.csv',index=False);pd.DataFrame(points,columns=list(points[0]) if points else ['target_source_record_id','coordinate_admission_status']).to_csv(OUT/'candidate_point_use_delta.csv',index=False);pd.DataFrame(holds).to_csv(OUT/'held_pairs.csv',index=False)
 receipt={'status':'candidate_only_simulated_no_admission','candidate_edges':len(edges),'candidate_point_uses':len(points),'baseline':before,'simulated_after':after,'simulated_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'simulated_full_three_year_row_gain':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'outcomes':dict(outcomes),'inputs_sha256':inputs,'point_ledger_hashes':ledgerhash,'protected_2010_population_modified':False,'population_comparability_asserted':False,'normalization_rule':'NFKC casefold ё→е Unicode punctuation→space whitespace collapse','uniqueness_grain':'per year pair, all already accepted pointed exact-name same-region records within 5km; county and printed type ignored','point_independence_claim':False,'outputs_sha256':{p.name:sha(p) for p in OUT.glob('*.csv')}}
 (OUT/'simulation_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['candidate_edges','candidate_point_uses','simulated_population_gain','outcomes']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
