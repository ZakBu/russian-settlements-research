"""Candidate-only exact orthographic name bridge within explicit source county and region."""
import sys,json,re,random
from pathlib import Path
from collections import Counter,defaultdict
import pandas as pd
import pyarrow.parquet as pq
ROOT=Path('/workspace/russian-settlements-research')
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,E
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
from measure_event_aware_path_union_20261005 import SELECTED
OUT=E/'orthographic_name_bridge_20261007'
EVENT_ROWS=E/'event_aware_path_union_20261005/accepted_event_path_selected_rows.csv'
EVENT_CODES=Path('/workspace/settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json')
def exact_name(value):
 import unicodedata
 return " ".join(unicodedata.normalize("NFKC",str(value or "")).lower().split())

def station_alias(value):
 text=exact_name(value);original=text;flags=[]
 if 'ё' in text: text=text.replace('ё','е');flags.append('yo_to_e')
 quotes='«»„“”'
 if any(ch in text for ch in quotes):
  text=text.translate(str.maketrans('', '',quotes));flags.append('russian_quotation_marks')
 dashes='‐‑‒–—−'
 if any(ch in text for ch in dashes):
  text=text.translate(str.maketrans({ch:'-' for ch in dashes}));flags.append('unicode_dash_to_hyphen')
 canonical=re.sub(r'\s*-\s*','-',text)
 if canonical!=text: flags.append('whitespace_around_hyphen');text=canonical
 text=' '.join(text.split())
 return text,';'.join(flags)

def main():
 s=load(stage=10); before=s.metrics(); inputs={str(p):sha(p) for p in s.inputs}
 meta=pq.read_table(SELECTED,columns=['source_record_id','entity_grain_status','source_sheet','source_row','source_name_raw']).to_pandas().set_index('source_record_id')
 event_ids=set(pd.read_csv(EVENT_ROWS,usecols=['source_record_id'],dtype=str).source_record_id); codes=set()
 for r in json.loads(EVENT_CODES.read_text()):
  for k in ('from_settlement_id_legacy_candidate','to_settlement_id_legacy_candidate'):
   v=str(r.get(k) or '')
   if v.startswith(('RU-OKTMO-','RU-OKATO-')): codes.add(normalize(v.rsplit('-',1)[-1]))
 inputs.update({str(p):sha(p) for p in [EVENT_ROWS,EVENT_CODES]})
 obs=s.obs.copy(); obs['raw_exact_name']=obs.settlement_name.map(exact_name);obs['n']=obs.settlement_name.map(lambda v:station_alias(v)[0]);obs['orthographic_name_variant_removed']=obs.settlement_name.map(lambda v:station_alias(v)[1]);obs['r']=obs.region_norm.map(normalize);obs['d']=obs.district_raw.map(county_key)
 obs=obs.join(meta,on='source_record_id')
 whole=obs.is_additive_settlement_record.fillna(False) & ~obs.settlement_type.fillna('').str.contains(r'железнодорожный объект|railway.?feature|административ',case=False,regex=True) & ~obs.settlement_name.fillna('').str.contains(r'\(часть|\b(?:район|муниципальн(?:ый|ое|ая)|городское население|сельское население|итого|всего)\b',regex=True,case=False) & ~obs.entity_grain_status.fillna('').str.contains('aggregate|municipal|parent|control_total',case=False,regex=True)
 # Per-year uniqueness counts all whole source rows with explicit county, before event filtering.
 obs['eligible_physical_whole']=whole
 # Count unresolved source-name competitors even when their additive status is not admitted.
 plausible=~obs.settlement_name.fillna('').str.contains(r'\(часть|\b(?:район|муниципальн(?:ый|ое|ая)|городское население|сельское население|итого|всего)\b',regex=True,case=False) & ~obs.entity_grain_status.fillna('').str.contains('aggregate|municipal|parent|control_total',case=False,regex=True)
 obs=obs[plausible & obs.n.ne('') & obs.d.str.len().ge(3) & ~obs.r.isin(['москва','санкт петербург','севастополь'])].copy()
 obs['key_count']=obs.groupby(['census_year','n','r','d']).source_record_id.transform('size')
 unique=obs[obs.eligible_physical_whole & obs.key_count.eq(1) & ~obs.entity_grain_status.fillna('').str.contains('unresolved',case=False,regex=True)]
 members=defaultdict(list)
 for sid in s.by_id.index: members[s.uf.find(sid)].append(sid)
 collisions=Counter((int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude']) for sid,p in s.point_rows.items())
 original_points=set(s.point_rows); edges=[];points=[];holds=[];reserves=[]; outcomes=Counter(); seen=set();ledger_hashes={}
 for ya,yb in [(2002,2010),(2010,2021),(2002,2021)]:
  pairs=unique[unique.census_year.eq(ya)].merge(unique[unique.census_year.eq(yb)],on=['n','r','d'],suffixes=('_a','_b')).sort_values(['population_a','population_b'],ascending=False)
  for row in pairs.to_dict('records'):
   if row['raw_exact_name_a']==row['raw_exact_name_b'] or not (row['orthographic_name_variant_removed_a'] or row['orthographic_name_variant_removed_b']):continue
   a,b=row['source_record_id_a'],row['source_record_id_b'];ra,rb=s.uf.find(a),s.uf.find(b)
   if ra==rb: outcomes['already_connected']+=1;continue
   if frozenset([ra,rb]) in seen: outcomes['duplicate_component_pair']+=1;continue
   seen.add(frozenset([ra,rb]));m=members[ra]+members[rb]
   donor_ids=[x for x in m if x in original_points]
   if not donor_ids:
    outcomes['no_previously_accepted_component_point']+=1
    reserve={'from_source_record_id':a,'to_source_record_id':b,'name_norm':row['n'],'county_key':row['d'],'region_norm':row['r'],'reason':'no_previously_accepted_component_point_not_a_candidate_edge'}
    for side,prefix in [('a','from'),('b','to')]:
     for field in ['settlement_name','district_raw','source_file','source_sha256','source_locator','source_sheet','source_row','population','census_year']:reserve[prefix+'_'+field]=row[field+'_'+side]
    reserves.append(reserve);continue
   donor_id=max(donor_ids,key=lambda x:int(s.by_id.loc[x,'census_year']));donor=s.point_rows[donor_id];dp=(donor['latitude'],donor['longitude']);reasons=[]
   if s.years[ra]&s.years[rb]:reasons.append('repeated_year_component')
   for x in m:
    rr=s.by_id.loc[x]
    if not bool(rr.is_additive_settlement_record) or re.search(r'\(часть',str(rr.settlement_name),re.I) or re.search(r'железнодорожный объект|railway.?feature|административ',str(rr.settlement_type),re.I):reasons.append('component_member_not_physical_whole_np')
    if x in event_ids or any(normalize(rr[k]) in codes for k in ['oktmo','okato']): reasons.append('known_event_member')
    if x in s.conflicting_point_targets: reasons.append('conflicting_accepted_point_alternatives')
    p=s.point_rows.get(x)
    if p:
     if distance_km(dp,(p['latitude'],p['longitude']))>5:reasons.append('component_accepted_points_over_5km')
     if collisions[(int(rr.census_year),p['latitude'],p['longitude'])]>1: reasons.append('shared_same_year_accepted_point')
    lat,lon=rr.latitude,rr.longitude
    if pd.notna(lat) and pd.notna(lon) and -90<=lat<=90 and -180<=lon<=180 and (lat,lon)!=(0,0) and distance_km(dp,(lat,lon))>5:reasons.append('native_source_coordinate_contradiction')
   ap,bp=s.point_rows.get(a),s.point_rows.get(b)
   if ap and bp and distance_km((ap['latitude'],ap['longitude']),(bp['latitude'],bp['longitude']))>5:reasons.append('endpoint_accepted_points_over_5km')
   for x in m:
    if x not in s.point_rows and collisions[(int(s.by_id.loc[x,'census_year']),*dp)]>0:reasons.append('proposed_transfer_same_year_point_collision')
   if reasons:
    holds.append({'from_source_record_id':a,'to_source_record_id':b,'name_norm':row['n'],'county_key':row['d'],'reason':';'.join(sorted(set(reasons)))})
    outcomes.update(set(reasons));continue
   ap,bp=s.point_rows.get(a),s.point_rows.get(b)
   dist=distance_km((ap['latitude'],ap['longitude']),(bp['latitude'],bp['longitude'])) if ap and bp else None
   edge={'from_source_record_id':a,'to_source_record_id':b,'from_year':ya,'to_year':yb,'relation':'same_place','decision_status':'candidate_pending_independent_review','name_norm':row['n'],'region_norm':row['r'],'county_key':row['d'],'possible_type_change':normalize(row['settlement_type_a'])!=normalize(row['settlement_type_b']),'from_type_raw':row['settlement_type_a'],'to_type_raw':row['settlement_type_b'],'from_district_raw':row['district_raw_a'],'to_district_raw':row['district_raw_b'],'from_population':row['population_a'],'to_population':row['population_b'],'distance_km_if_both_points':dist,'previous_component_years_from':','.join(map(str,sorted(s.years[ra]))),'previous_component_years_to':','.join(map(str,sorted(s.years[rb]))),'point_donor_source_record_id':donor_id,'point_donor_ledger':donor['point_ledger_path'],'same_year_point_collision':False,'event_collision':False,'native_coordinate_contradiction':False,'repeated_year_collision':False,'per_year_name_region_county_unique_ignoring_type':True,'population_comparability_asserted':False,'native_code_binding_asserted':False,'orthographic_name_variant_is_legal_rename':False,'from_orthographic_name_variant_removed':row['orthographic_name_variant_removed_a'],'to_orthographic_name_variant_removed':row['orthographic_name_variant_removed_b'],'admission_rule':'orthographic_name_variant_alias_exact_name_region_explicit_county_unique_ignoring_type_accepted_component_point_5km_v1'}
   for side in ['a','b']:
    prefix='from' if side=='a' else 'to'
    for field in ['settlement_name','source_file','source_sha256','source_locator','source_sheet','source_row','source_name_raw','entity_grain_status']:
     edge[prefix+'_'+field]=row[field+'_'+side]
   ledger=Path(donor['point_ledger_path']);ledger_hashes.setdefault(str(ledger),sha(ledger));edge['point_donor_ledger_sha256']=ledger_hashes[str(ledger)];edge['point_donor_ledger_locator']='target_source_record_id='+donor_id
   edges.append(edge);s.union(a,b);root=s.uf.find(a);members[root]=m
   for x in m:
    if x in s.point_rows:continue
    rr=s.by_id.loc[x]
    # Transfer only if no different same-year object already owns this representative point.
    if collisions[(int(rr.census_year),*dp)]>0:raise ValueError('New transfer would collide')
    p={'target_source_record_id':x,'target_year':int(rr.census_year),'latitude':dp[0],'longitude':dp[1],'coordinate_source_record_id':donor_id,'coordinate_admission_status':'candidate_pending_independent_review','coordinate_origin_ledger':str(ledger),'coordinate_origin_ledger_sha256':ledger_hashes[str(ledger)],'coordinate_origin_ledger_locator':'target_source_record_id='+donor_id,'admission_rule':'representative_point_continuity_over_proposed_orthographic_name_variant_county_name_identity','direct_historical_coordinate_measurement':False,'native_code_binding_asserted':False,'boundary_comparability_asserted':False}
    points.append(p);s.point_rows[x]=dict(p,point_ledger_path=str(OUT/'candidate_point_use_delta.csv'));collisions[(int(rr.census_year),*dp)]+=1
 after=s.metrics()
 pd.DataFrame(reserves,columns=list(reserves[0]) if reserves else ['from_source_record_id','to_source_record_id','reason']).to_csv(OUT/'no_point_reserve.csv',index=False)
 pd.DataFrame(edges,columns=list(edges[0]) if edges else ['from_source_record_id','to_source_record_id']).to_csv(OUT/'candidate_identity_edge_delta.csv',index=False);pd.DataFrame(points,columns=list(points[0]) if points else ['target_source_record_id']).to_csv(OUT/'candidate_point_use_delta.csv',index=False)
 pd.DataFrame(holds,columns=list(holds[0]) if holds else ['from_source_record_id','to_source_record_id','reason']).to_csv(OUT/'held_pairs.csv',index=False)
 receipt={'status':'candidate_only_simulated_no_admission','candidate_edges':len(edges),'candidate_point_uses':len(points),'possible_type_change_edges':sum(x['possible_type_change'] for x in edges),'baseline':before,'simulated_after':after,'simulated_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'outcomes':dict(outcomes),'inputs_sha256':inputs,'point_donor_ledger_hashes':ledger_hashes,'protected_2010_population_modified':False,'letters_preserved_except_explicit_yo_e_equivalence':True,'numbers_preserved':True,'no_fuzzy_matching':True,'working_state_stage':10,'simulation_order':'2002-2010,2010-2021,2002-2021; each descending endpoint population; population is scheduling only','candidate_not_accepted':True,'outputs_sha256':{p.name:sha(p) for p in OUT.glob('*.csv')}}
 (OUT/'simulation_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:receipt[k] for k in ['candidate_edges','candidate_point_uses','possible_type_change_edges','simulated_population_gain','outcomes']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
