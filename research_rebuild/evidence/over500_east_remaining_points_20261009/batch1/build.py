from pathlib import Path
import pandas as pd,re,json,gzip,hashlib
O=Path(__file__).parent;B=O.parent;D=pd.read_pickle('/dev/shm/over500-20261009/east_enriched.pkl');R=pd.read_csv(B/'remaining81_native_point_targets.csv').fillna('');G=pd.read_csv('research_rebuild/evidence/over500_east_alternative_point_sources_20261009/geonames_cached_own_place_candidates.csv.gz').fillna('');N=pd.read_csv('research_rebuild/evidence/over500_east_alternative_point_sources_20261009/nominatim_own_feature_candidates.csv.gz').fillna('');norm=lambda s:' '.join(re.sub('[^а-я0-9 ]',' ',str(s).lower().replace('ё','е')).split())
def ownkeys(s):
 a={norm(s)}
 if '('in s:
  a.add(norm(s.split('(')[0]));a.add(norm(s.split('(')[1].split(')')[0]))
 a.add(re.sub(r'^участок\s+','',norm(s)))
 return a
D['ownkeys']=D.settlement_name.map(ownkeys);points=[];w=[];di=[]
for t in R.itertuples():
 g=G[G.source_record_id.eq(t.source_record_id)]
 if len(g)!=1:continue
 p=g.iloc[0];keys=ownkeys(t.settlement_name)
 if norm(p.matched_name)not in keys or p.feature_class!='P'or p.feature_code not in ['PPL','PPLX','PPLA3','PPLA4','PPLH','PPLQ']:continue
 rivals=D[D.census_year.eq(t.census_year)&D.region_norm.eq(t.region_norm)&D.ownkeys.map(lambda x:bool(x&keys))]
 if len(rivals)!=1:continue
 alternatives=N[N.source_record_id.eq(t.source_record_id)&N.feature_category.eq('place')]
 # A unique GeoNames origin is rejected if an independently identified same-name ownplace differs >5km without resolution.
 # Exact own named objects only: nearby hamlets qualified by Верхнее/Нижнее do not compete with a literal plain name.
 ownalts=alternatives[alternatives.own_name.map(norm).isin(keys)]
 if len(ownalts):
  import math
  close=[]
  for a in ownalts.itertuples():
   dist=6371*2*math.asin(min(1,math.sqrt(math.sin(math.radians(a.latitude-p.latitude)/2)**2+math.cos(math.radians(p.latitude))*math.cos(math.radians(a.latitude))*math.sin(math.radians(a.longitude-p.longitude)/2)**2)));close.append(dist)
  if min(close)>5:continue
 wid=len(w);w.append(dict(target_source_record_id=t.source_record_id,source_name_raw=t.settlement_name,source_type_raw=t.settlement_type,source_county_raw=t.district_raw,source_region=t.region_norm,source_year=t.census_year,all_type_sourceyear_region_literal_ownname_rivals=rivals[['source_record_id','settlement_name','type_norm','county']].to_dict('records'),direct_GeoNames_raw_record=p.to_dict(),provider_admin2_status='MISSING'if not p.admin2_code else'published_raw',native_county_binding_asserted=False,own_name_binding_rule='Literal own name or native explicitly printed parenthetical alias / Участок locality designator, unique across all native physical types for selected sourceyear and subject; unique actualGeoNames populatedplace feature in subject. Independent own OSM named alternatives compared where returned.',retrospective_point_use_is_continuity_inference=True,point_accuracy='Provider representative localitypoint; ownsitebinding supported, exact historical censusday coordinate and precision unknown.'))
 points.append(dict(target_source_record_id=t.source_record_id,latitude=p.latitude,longitude=p.longitude,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=f'geonames:{int(p.geonameid)}',point_origin_file=p.source_file,point_origin_sha256=p.source_sha256,point_origin_locator=p.source_locator,point_origin_kind='direct_GeoNames_own_named_populated_locality_coordinate',coordinate_binding_rule='unique_all_native_type_sourceyear_region_literal_ownname_and_unique_direct_GeoNames_place',point_use_inference='Explicit retrospective own-locality representative point inference; actual physical place grain preserved. Censusday coordinate, measurement accuracy and exact population boundaries unknown.',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,external_provider_ID_binding_asserted=True,evidence_file=str(O/'point_binding_witnesses.json.gz'),evidence_locator=f'[{wid}]'))
 di.append(dict(source_record_id=t.source_record_id,disposition='accepted_direct_source_bound_GeoNames_own_place_point',ordinary_identity_edges_added=False,missing_year_population_assigned=False))
with gzip.open(O/'point_binding_witnesses.json.gz','wt')as f:json.dump(w,f,ensure_ascii=False)
pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(columns=['from_source_record_id','to_source_record_id','relation','decision_status','admission_method','admission_rule','evidence_file','evidence_locator']).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(di).to_csv(O/'record_dispositions.csv',index=False);print(len(points));print([(x['source_name_raw'],x['direct_GeoNames_raw_record']['feature_name'])for x in w])
