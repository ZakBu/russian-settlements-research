"""Exact compatible printed type-prefix aliases; candidate generation, never admission."""
import sys,json,re,unicodedata
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
OUT=Path(__file__).resolve().parent
STAGE=10
EVENT_ROWS=E/'event_aware_path_union_20261005/accepted_event_path_selected_rows.csv'
EVENT_CODES=Path('/workspace/settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json')
def exact_name(value):
 return ' '.join(unicodedata.normalize('NFKC',str(value or '')).lower().split())
PREFIX_TYPES={'п':{'поселок'},'п.':{'поселок'},'пос.':{'поселок'},'г':{'город'},'г.':{'город'},'с':{'село'},'с.':{'село'},'д':{'деревня'},'д.':{'деревня'},'дер.':{'деревня'},'х':{'хутор'},'х.':{'хутор'},'ст':{'станица','станция','железнодорожная станция'},'ст.':{'станица','станция','железнодорожная станция'},'пгт':{'поселок городского типа','пгт'}}
def alias(name,typ):
 n=exact_name(name);t=normalize(typ);prefix,space,rest=n.partition(' ')
 if space and rest and prefix in PREFIX_TYPES and t in PREFIX_TYPES[prefix]:return rest,prefix+' '
 return n,''
def main():
 s=load(STAGE);before=s.metrics();inputs={str(p):sha(p) for p in s.inputs}
 coverage_path=E/'working_full_chain_20261007/coverage_receipt.json';coverage=json.loads(coverage_path.read_text());assert coverage['working_stage']==STAGE
 baseline_axes={}
 for y,m in before.items():
  ref=coverage['ordinary_axes_by_year'][y];joint=ref['axes']['point_and_full_three_census_identity'];full=ref['axes']['full_three_census_identity_link']
  assert m['covered_population']==joint['population'] and m['covered_rows']==joint['rows'] and m['denominator_selected_ordinary_population']==ref['denominator_population'],'Published baseline mismatch'
  dd=s.obs[s.obs.is_additive_settlement_record.fillna(False)&s.obs.census_year.eq(int(y))&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь'])]
  if int(y)==2021:dd=dd[~dd.region_norm.eq('крым')]
  mask=dd.source_record_id.map(lambda x:s.years[s.uf.find(x)]=={2002,2010,2021})
  assert int(mask.sum())==full['rows'] and int(dd.loc[mask,'population'].sum())==full['population'],'Published full-three identity baseline mismatch'
  baseline_axes[y]={'full_three_census_identity_rows':full['rows'],'full_three_census_identity_population':full['population'],'joint_point_full_three_rows':joint['rows'],'joint_point_full_three_population':joint['population']}
 inputs[str(coverage_path)]=sha(coverage_path)
 meta=pq.read_table(SELECTED,columns=['source_record_id','entity_grain_status','source_sheet','source_row','source_name_raw']).to_pandas().set_index('source_record_id')
 event_ids=set(pd.read_csv(EVENT_ROWS,usecols=['source_record_id'],dtype=str).source_record_id);codes=set()
 for row in json.loads(EVENT_CODES.read_text()):
  for k in ('from_settlement_id_legacy_candidate','to_settlement_id_legacy_candidate'):
   v=str(row.get(k) or '')
   if v.startswith(('RU-OKTMO-','RU-OKATO-')):codes.add(normalize(v.rsplit('-',1)[-1]))
 inputs.update({str(p):sha(p) for p in [EVENT_ROWS,EVENT_CODES,SELECTED]})
 obs=s.obs.join(meta,on='source_record_id').copy();obs['raw_exact_name']=obs.settlement_name.map(exact_name)
 vals=[alias(n,t) for n,t in obs[['settlement_name','settlement_type']].itertuples(index=False,name=None)]
 obs['n']=[v[0] for v in vals];obs['prefix_removed']=[v[1] for v in vals];obs['r']=obs.region_norm.map(normalize);obs['d']=obs.district_raw.map(county_key)
 plausible=~obs.settlement_name.fillna('').str.contains(r'\(часть|\b(?:район|муниципальн(?:ый|ое|ая)|городское население|сельское население|итого|всего)\b',regex=True,case=False)&~obs.entity_grain_status.fillna('').str.contains('aggregate|municipal|parent|control_total',case=False,regex=True)
 whole=plausible & obs.is_additive_settlement_record.fillna(False)&~obs.entity_grain_status.fillna('').str.contains('unresolved',case=False,regex=True)&~obs.settlement_type.fillna('').str.contains(r'железнодорожный объект|railway.?feature|административ',case=False,regex=True)
 obs['whole']=whole
 obs=obs[plausible&obs.n.ne('')&~obs.r.isin(['москва','санкт петербург','севастополь'])].copy()
 obs['region_count']=obs.groupby(['census_year','n','r']).source_record_id.transform('size')
 obs['county_count']=obs.groupby(['census_year','n','r','d']).source_record_id.transform('size')
 prefix_keys=set(zip(obs.loc[obs.prefix_removed.ne(''),'n'],obs.loc[obs.prefix_removed.ne(''),'r']))
 eligible=obs[obs.whole & pd.Series([(n,r) in prefix_keys for n,r in obs[['n','r']].itertuples(index=False,name=None)],index=obs.index)]
 members=defaultdict(list)
 for sid in s.by_id.index:members[s.uf.find(sid)].append(sid)
 collisions=Counter((int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude']) for sid,p in s.point_rows.items())
 original_points=set(s.point_rows);edges=[];points=[];holds=[];reserves=[];outcomes=Counter();seen=set();ledger_hashes={}
 for ya,yb in [(2002,2010),(2010,2021),(2002,2021)]:
  pairs=eligible[eligible.census_year.eq(ya)].merge(eligible[eligible.census_year.eq(yb)],on=['n','r'],suffixes=('_a','_b')).sort_values(['population_a','population_b'],ascending=False)
  for row in pairs.to_dict('records'):
   if row['raw_exact_name_a']==row['raw_exact_name_b'] or not(row['prefix_removed_a'] or row['prefix_removed_b']):continue
   a,b=row['source_record_id_a'],row['source_record_id_b'];ra,rb=s.uf.find(a),s.uf.find(b)
   if ra==rb:outcomes['already_connected']+=1;continue
   da,db=row['d_a'],row['d_b'];county=da if len(da)>=3 else db
   explicit=len(da)>=3 and len(db)>=3
   if explicit and da!=db:outcomes['different_source_counties']+=1;continue
   if explicit:
    if row['county_count_a']!=1 or row['county_count_b']!=1:outcomes['nonunique_county_alias_ignoring_type']+=1;continue
    # A source without county is an unresolved plausible competitor for this county.
    for year in [ya,yb]:
     if ((obs.census_year==year)&(obs.n==row['n'])&(obs.r==row['r'])&(obs.d.str.len()<3)).any():break
    else:year=None
    if year is not None:outcomes['missing_county_alias_competitor']+=1;continue
   elif row['region_count_a']!=1 or row['region_count_b']!=1:outcomes['missing_county_nonunique_region_alias']+=1;continue
   if frozenset([ra,rb]) in seen:outcomes['duplicate_component_pair']+=1;continue
   seen.add(frozenset([ra,rb]));m=members[ra]+members[rb]
   ad=[x for x in members[ra] if x in original_points];bd=[x for x in members[rb] if x in original_points];donor_ids=ad+bd
   common={'from_source_record_id':a,'to_source_record_id':b,'name_norm':row['n'],'county_key':county,'region_norm':row['r']}
   if not donor_ids or (not explicit and not(ad and bd)):
    reserves.append(dict(common,reason='no_accepted_component_point' if not donor_ids else 'missing_county_requires_accepted_points_both_components',from_settlement_name=row['settlement_name_a'],to_settlement_name=row['settlement_name_b'],from_population=row['population_a'],to_population=row['population_b']));outcomes[reserves[-1]['reason']]+=1;continue
   donor_id=max(donor_ids,key=lambda x:int(s.by_id.loc[x,'census_year']));donor=s.point_rows[donor_id];dp=(donor['latitude'],donor['longitude']);reasons=[]
   if s.years[ra]&s.years[rb]:reasons.append('repeated_year_component')
   for x in m:
    rr=s.by_id.loc[x];cx=county_key(rr.district_raw)
    if len(cx)>=3 and len(county)>=3 and cx!=county:reasons.append('component_source_county_contradiction')
    if not bool(rr.is_additive_settlement_record) or re.search(r'\(часть',str(rr.settlement_name),re.I) or re.search(r'железнодорожный объект|railway.?feature|административ',str(rr.settlement_type),re.I):reasons.append('component_not_physical_whole_np')
    if x in event_ids or any(normalize(rr[k]) in codes for k in ['oktmo','okato']):reasons.append('known_event_member')
    if x in s.conflicting_point_targets:reasons.append('conflicting_accepted_point_alternatives')
    p=s.point_rows.get(x)
    if p:
     if distance_km(dp,(p['latitude'],p['longitude']))>5:reasons.append('accepted_points_over_5km')
     if collisions[(int(rr.census_year),p['latitude'],p['longitude'])]>1:reasons.append('shared_same_year_accepted_point')
    lat,lon=rr.latitude,rr.longitude
    if pd.notna(lat) and pd.notna(lon) and -90<=lat<=90 and -180<=lon<=180 and (lat,lon)!=(0,0) and distance_km(dp,(lat,lon))>5:reasons.append('native_source_coordinate_contradiction')
    if x not in s.point_rows and collisions[(int(rr.census_year),*dp)]>0:reasons.append('proposed_transfer_same_year_point_collision')
   if reasons:holds.append(dict(common,reason=';'.join(sorted(set(reasons)))));outcomes.update(set(reasons));continue
   edge=dict(common,from_year=ya,to_year=yb,relation='same_place',decision_status='candidate_pending_independent_review',possible_type_change=normalize(row['settlement_type_a'])!=normalize(row['settlement_type_b']),from_type_raw=row['settlement_type_a'],to_type_raw=row['settlement_type_b'],from_district_raw=row['district_raw_a'],to_district_raw=row['district_raw_b'],from_population=row['population_a'],to_population=row['population_b'],from_prefix_removed=row['prefix_removed_a'],to_prefix_removed=row['prefix_removed_b'],county_rule='explicit_same_county' if explicit else 'region_unique_accepted_points_both_components',previous_component_years_from=','.join(map(str,sorted(s.years[ra]))),previous_component_years_to=','.join(map(str,sorted(s.years[rb]))),point_donor_source_record_id=donor_id,point_donor_ledger=donor['point_ledger_path'],per_year_alias_unique_ignoring_type=True,population_comparability_asserted=False,native_code_binding_asserted=False,prefix_alias_is_legal_rename=False,admission_rule='compatible_native_printed_type_prefix_exact_alias_county_or_both_point_unique_region_v1')
   for side,prefix in [('a','from'),('b','to')]:
    for field in ['settlement_name','source_file','source_sha256','source_locator','source_sheet','source_row','source_name_raw','entity_grain_status']:edge[prefix+'_'+field]=row[field+'_'+side]
   ledger=Path(donor['point_ledger_path']);ledger_hashes.setdefault(str(ledger),sha(ledger));edge.update(point_donor_ledger_sha256=ledger_hashes[str(ledger)],point_donor_ledger_locator='target_source_record_id='+donor_id)
   edges.append(edge);s.union(a,b);members[s.uf.find(a)]=m
   for x in m:
    if x in s.point_rows:continue
    rr=s.by_id.loc[x];p={'target_source_record_id':x,'target_year':int(rr.census_year),'latitude':dp[0],'longitude':dp[1],'coordinate_source_record_id':donor_id,'coordinate_admission_status':'candidate_pending_independent_review','coordinate_origin_ledger':str(ledger),'coordinate_origin_ledger_sha256':ledger_hashes[str(ledger)],'coordinate_origin_ledger_locator':'target_source_record_id='+donor_id,'admission_rule':'representative_point_continuity_over_proposed_native_type_prefix_exact_alias_identity','direct_historical_coordinate_measurement':False,'native_code_binding_asserted':False,'boundary_comparability_asserted':False}
    points.append(p);s.point_rows[x]=dict(p,point_ledger_path=str(OUT/'candidate_point_use_delta.csv'));collisions[(int(rr.census_year),*dp)]+=1
 for name,rows,cols in [('candidate_identity_edge_delta',edges,['from_source_record_id','to_source_record_id']),('candidate_point_use_delta',points,['target_source_record_id']),('held_pairs',holds,['from_source_record_id','to_source_record_id','reason']),('no_point_reserve',reserves,['from_source_record_id','to_source_record_id','reason'])]:pd.DataFrame(rows,columns=list(rows[0]) if rows else cols).to_csv(OUT/(name+'.csv'),index=False)
 after=s.metrics();receipt={'status':'candidate_only_simulated_no_admission','working_state_stage':STAGE,'baseline':before,'published_full_and_joint_baseline_verified':baseline_axes,'simulated_after':after,'simulated_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'candidate_edges':len(edges),'candidate_point_uses':len(points),'outcomes':dict(outcomes),'inputs_sha256':inputs,'point_donor_ledger_hashes':ledger_hashes,'prefix_types':{k:sorted(v) for k,v in PREFIX_TYPES.items()},'letters_numbers_preserved':True,'no_fuzzy_matching':True,'population_values_modified':False,'outputs_sha256':{p.name:sha(p) for p in OUT.glob('*.csv')}}
 (OUT/'simulation_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['candidate_edges','candidate_point_uses','simulated_population_gain','outcomes']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
