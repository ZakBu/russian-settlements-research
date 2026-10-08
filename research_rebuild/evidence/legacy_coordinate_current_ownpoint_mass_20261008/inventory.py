from pathlib import Path
import sys,json,math,ast,collections
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;E=O.parent;s=load(32);pins={str(p):sha(p)for p in s.inputs};aliaspath=E/'cross_county_independent_point_bridge_20261007/build_neutral_subset.py';tree=ast.parse(aliaspath.read_text());pairs=ast.literal_eval(next(x.value for x in tree.body if isinstance(x,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='pairs'for t in x.targets)));neutral={frozenset([county_key(a),county_key(b)])for a,b in pairs.items()};pins[str(aliaspath)]=sha(aliaspath)
ctx=Path('/workspace/settlements-work/secondary_2010_county_context_batch_20261007/all_selected_competitor_county_context.csv.gz');context=pd.read_csv(ctx,dtype=str,keep_default_na=False).set_index('source_record_id').to_dict('index');pins[str(ctx)]=sha(ctx)
def code(v):
 if pd.isna(v):return ''
 x=str(v).strip();return x[:-2]if x.endswith('.0')else x
AUX=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet');con=duckdb.connect(config={'threads':1,'memory_limit':'300MB'});aux=con.execute('select source_record_id,latitude_from_lat auxiliary_latitude,longitude_from_long auxiliary_longitude,historical_okato auxiliary_candidate_historical_code from read_parquet(?)where census_year in(2002,2010)and latitude_from_lat is not null',[str(AUX)]).fetchdf();assert not aux.source_record_id.duplicated().any();pins[str(AUX)]=sha(AUX)
obs=s.obs.copy().merge(aux,on='source_record_id',how='left',validate='one_to_one');obs['latitude']=obs.latitude.fillna(obs.auxiliary_latitude);obs['longitude']=obs.longitude.fillna(obs.auxiliary_longitude);obs['n']=obs.name_norm.map(normalize);obs['r']=obs.region_norm.map(normalize);obs['t']=obs.type_norm.map(normalize);obs['county']=obs.district_raw.map(county_key);obs['code']=obs.okato.map(code)
obs.loc[obs.county.eq(''),'county']=obs.loc[obs.county.eq(''),'source_record_id'].map(lambda x:context.get(x,{}).get('inferred_county_key',''))
current=collections.defaultdict(list);oldidx=collections.defaultdict(list);members=collections.defaultdict(list)
for a in obs.to_dict('records'):
 sid=a['source_record_id'];members[s.uf.find(sid)].append(sid)
 if a['census_year']==2021 and a['is_additive_settlement_record'] and sid in s.point_rows:current[(a['n'],a['r'])].append(a)
 if a['census_year'] in [2002,2010] and a['is_additive_settlement_record']:oldidx[(int(a['census_year']),a['n'],a['r'])].append(a)
credited=set()
for p in [E/'working_full_chain_20261007/qualified_physical_observations.csv',E/'working_full_chain_20261007/named_merger_lineage_constituents.csv',E/'working_full_chain_20261007/complete_territorial_scope_constituents.csv']:
 f=pd.read_csv(p,dtype=str,keep_default_na=False);pins[str(p)]=sha(p)
 for c in f:
  if c=='source_record_id':credited.update(f[c])
counts=collections.Counter();candidates=[];held=[];raw=obs[obs.census_year.isin([2002,2010])&obs.is_additive_settlement_record.fillna(False)&obs.latitude.between(41,82)&obs.longitude.between(19,180)&~obs.r.isin(['чеченская','московская'])].copy();raw=raw.loc[raw.source_record_id.map(lambda x:x not in s.point_rows or s.years[s.uf.find(x)]!={2002,2010,2021}).astype(bool)];rawsummary=raw.groupby(['census_year','r']).agg(rows=('source_record_id','size'),population=('population','sum')).reset_index();rawsummary.to_csv(O/'residual_raw_coordinate_inventory_by_region.csv',index=False)
for a in raw.to_dict('records'):
 sid=a['source_record_id'];near=[]
 for b in current.get((a['n'],a['r']),[]):
  p=s.point_rows[b['source_record_id']];dist=distance_km((a['latitude'],a['longitude']),(p['latitude'],p['longitude']))
  if dist<=5:near.append((b,dist))
 if len(near)!=1:counts['no_unique_current_ownpoint_5km_before_graph_filter']+=1;continue
 b,dist=near[0];bid=b['source_record_id'];ra,rb=s.uf.find(sid),s.uf.find(bid);same=bool(a['county'])and(a['county']==b['county']or frozenset([a['county'],b['county']])in neutral);direct=bool(a['code'])and a['code']==b['code'];reason=''
 if not(same or direct or ra==rb):reason='native_printed_or_existing_flanking_county_and_owncode_not_positive'
 if a['code']and b['code']and a['code']!=b['code']and not same:reason='unexplained_actual_native_code_contradiction'
 if any(z in a['t']or z in b['t']for z in ['объект','станци','разъезд','участок']):reason='nonstandard_or_railway_locality_grain_needs_positive_own_binding'
 if a['t']in ['город','пгт']and b['t']not in ['город','пгт','поселок']:reason='incompatible_actual_native_urban_type'
 if sid in credited or bid in credited:reason='existing_qualified_named_or_territorial_scope_reference'
 if ra!=rb and s.years[ra]&s.years[rb]:reason='actual_repeated_census_year_component'
 ids=members[ra]if ra==rb else members[ra]+members[rb]
 if any(x in s.conflicting_point_targets for x in ids):reason='unresolved_existing_accepted_point_alternative'
 cp=s.point_rows[bid]
 if any(x in s.point_rows and distance_km((s.point_rows[x]['latitude'],s.point_rows[x]['longitude']),(cp['latitude'],cp['longitude']))>5 for x in ids):reason='existing_admitted_component_point_conflict'
 if any(pd.isna(s.by_id.loc[x,'population'])or not math.isfinite(float(s.by_id.loc[x,'population']))for x in ids):reason='unknown_native_population'
 # All old same-year source alternatives considered, including existing complete histories.
 rivals=[]
 for x in oldidx[(int(a['census_year']),a['n'],a['r'])]:
  if x['source_record_id']==sid or(x['county']and a['county']and x['county']!=a['county']):continue
  if x['code']and a['code']and x['code']!=a['code']:continue
  if pd.notna(x['latitude'])and pd.notna(x['longitude'])and distance_km((x['latitude'],x['longitude']),(cp['latitude'],cp['longitude']))>5:continue
  rivals.append(x['source_record_id'])
 if rivals:reason='unresolved_same_year_native_own_locality_competitors'
 if reason:
  counts[reason]+=1
  if len(held)<100:held.append({'source_record_id':sid,'current_source_record_id':bid,'name':a['settlement_name'],'year':int(a['census_year']),'population':a['population'],'reason':reason})
  continue
 candidates.append({'from_source_record_id':sid,'to_source_record_id':bid,'from_year':int(a['census_year']),'name':a['settlement_name'],'region':a['r'],'old_type':a['settlement_type'],'current_type':b['settlement_type'],'old_population':a['population'],'current_population':b['population'],'old_county':a['district_raw'],'old_county_bound':a['county'],'current_county':b['district_raw'],'old_native_okato':a['code'],'current_native_okato':b['code'],'positive_county_context':same,'positive_direct_native_code':direct,'existing_same_place_component':ra==rb,'old_aux_latitude':a['latitude'],'old_aux_longitude':a['longitude'],'auxiliary_point_distance_km':dist,'old_aux_coordinate_identity_accepted':False,'old_auxiliary_source_file':str(AUX),'old_auxiliary_source_locator':'source_record_id='+sid+';latitude_from_lat,longitude_from_long','old_auxiliary_source_sha256':pins[str(AUX)],'all_current_same_name_region_competitor_count':len(current[(a['n'],a['r'])]),'current_5km_competitor_count':len(near),'component_years_if_joined':json.dumps(sorted(s.years[ra]|s.years[rb])),'would_make_full3':s.years[ra]|s.years[rb]=={2002,2010,2021},'missing_point_source_IDs_json':json.dumps([x for x in ids if x not in s.point_rows]),'component_source_IDs_json':json.dumps(ids),'current_own_point_json':json.dumps(cp,ensure_ascii=False),'old_source_file':a['source_file'],'old_source_locator':a['source_locator'],'candidate_status':'candidate_only_current_ownpoint_substitution_native_context_rule'})
f=pd.DataFrame(candidates);f.to_csv(O/'candidate_native_context_current_ownpoint.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(held).to_csv(O/'bounded_holds.csv',index=False)
if len(f):f.groupby(['from_year','region']).agg(candidate_rows=('from_source_record_id','size'),native_old_population=('old_population','sum'),would_make_full3=('would_make_full3','sum')).reset_index().to_csv(O/'positive_candidate_region_inventory.csv',index=False)
r={'status':'candidate_only_inventory','baseline_stage':32,'old_auxiliary_coordinate_rows':len(raw),'raw_coordinate_year_counts':{str(y):{'rows':len(g),'population':int(g.population.sum())}for y,g in raw.groupby('census_year')},'positive_candidates':len(f),'positive_by_year':{str(y):{'rows':len(g),'old_native_population':int(g.old_population.sum()),'full3_candidate_rows':int(g.would_make_full3.sum()),'full3_old_native_population':int(g.loc[g.would_make_full3,'old_population'].sum())}for y,g in f.groupby('from_year')}if len(f)else{},'outcomes':dict(counts),'old_auxiliary_coordinates_not_admitted_as_own':True,'current_alternatives_include_existing_full3_before_graph_filter':True,'excluded_regions':['чеченская','московская'],'input_pins':pins,'outputs':{p.name:sha(p)for p in O.glob('*.csv*')}};(O/'inventory_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:r[k]for k in ['old_auxiliary_coordinate_rows','raw_coordinate_year_counts','positive_candidates','positive_by_year','outcomes']},ensure_ascii=False))
