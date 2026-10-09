from pathlib import Path
import pandas as pd,json,gzip,math
O=Path(__file__).parent;D=pd.read_pickle('/dev/shm/over500-20261009/east_enriched.pkl');R=pd.read_csv(O.parent/'assigned.csv').fillna('');by=D.set_index('source_record_id');P=pd.read_parquet('/dev/shm/over500-20261009/points_compact.parquet').fillna('');par={}
def find(a):
 if a not in par:par[a]=a
 if par[a]!=a:par[a]=find(par[a])
 return par[a]
prior=[O.parent]+[O.parent/f'subbatch{k}'for k in range(2,6)]
for z in prior:
 E=pd.read_csv(z/'accepted_identity_edge_delta.csv');P=pd.concat([P,pd.read_csv(z/'accepted_point_use_delta.csv').fillna('')],ignore_index=True)
 for e in E.itertuples():par[find(by.loc[e.from_source_record_id,'root'])]=find(by.loc[e.to_source_record_id,'root'])
D['root']=D.root.map(find);by=D.set_index('source_record_id',drop=False);P=P.drop_duplicates('target_source_record_id',keep='last').set_index('target_source_record_id');edge=[];point=[];w=[];di=[];seen=set()
for r in R.itertuples():
 t=by.loc[r.source_record_id];group=D[D.region_norm.eq(t.region_norm)&D.name_norm.eq(t.name_norm)];ids=group.source_record_id.tolist()
 if group.census_year.duplicated().any()or group.root.nunique()<2 or len(group)<2:continue
 if any(x in t.name_norm for x in ['часть','и станция']):continue
 if group.county[group.county.ne('')].nunique()>1:continue
 types=set(group.type_norm);compatible=len(types)==1 or types<={'село','деревня','поселок'}
 if not compatible:continue
 whole=D[D.root.isin(group.root)]
 if whole.census_year.duplicated().any():continue
 donors=[P.loc[s]for s in whole.source_record_id if s in P.index]
 if not donors:continue
 coherent=True;a=donors[0]
 for p in donors[1:]:
  la,lo=float(a.latitude),float(a.longitude);lat,lon=float(p.latitude),float(p.longitude);dist=6371*2*math.asin(min(1,math.sqrt(math.sin(math.radians(lat-la)/2)**2+math.cos(math.radians(la))*math.cos(math.radians(lat))*math.sin(math.radians(lon-lo)/2)**2)))
  if dist>5:coherent=False
 if not coherent:continue
 if t.name_norm+'|'+t.region_norm in seen:continue
 seen.add(t.name_norm+'|'+t.region_norm);wid=len(w);w.append(dict(name=t.name_norm,region=t.region_norm,all_type_region_native_same_name_rivals=group[['source_record_id','census_year','type_norm','county','root']].to_dict('records'),accepted_point_donors=[dict(target_source_record_id=p.name,coordinate_source_record_id=p.coordinate_source_record_id,latitude=p.latitude,longitude=p.longitude,point_origin_file=p.point_origin_file,point_origin_sha256=p.point_origin_sha256)for p in donors],one_native_record_per_year=True,known_counties_noncontradictory=True,compatible_physical_locality_types=True,population_boundary_equivalence=False,rule='Existing ordinary stable whole-region-unique literal name and compatible physical locality type, with independently accepted ownpoint, all-type rivals and sourcecomponentyear contradictions blocked.'))
 anchor=group.source_record_id.iloc[0];anchorroot=group.root.iloc[0]
 for m in group.itertuples():
  if m.root==anchorroot:continue
  edge.append(dict(from_source_record_id=anchor,to_source_record_id=m.source_record_id,relation='same_place',decision_status='checked_rule_accepted',admission_method='ordinary_stable_region_unique_literal_name_compatible_type_accepted_ownpoint',admission_rule='All-type own native locality name unique in subject for each observedyear; published physical locality types compatible; known county captions noncontradictory; independently accepted ownpoint coordinates consistent within5km. Missing year remains unknown; no boundary equality or legal category-change claim.',population_boundary_comparability_asserted=False,evidence_file=str(O/'identity_point_witnesses.json.gz'),evidence_locator=f'[{wid}]'));anchorroot=m.root
 donor=next((P.loc[s]for s in whole[whole.census_year.eq(2021)].source_record_id if s in P.index),a)
 for sid in whole.source_record_id:
  if sid in P.index:continue
  point.append(dict(target_source_record_id=sid,**{k:donor[k]for k in ['latitude','longitude','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind']},coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_binding_rule='ordinary_stable_region_unique_literal_name_compatible_type_accepted_ownpoint',point_use_inference='Accepted own locality representative point carried retrospectively by explicit stable continuity inference; missing counts stayunknown; exact censusdate coordinate and populationboundarycomparability unknown.',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,external_provider_ID_binding_asserted=False,current_carrier_source_record_id=donor.name))
 for sid in whole.source_record_id:di.append(dict(source_record_id=sid,disposition='accepted_existing_ordinary_stable_region_unique_literal_own_name_rule',observed_years=','.join(map(str,sorted(whole.census_year)))))
with gzip.open(O/'identity_point_witnesses.json.gz','wt')as f:json.dump(w,f,ensure_ascii=False)
pd.DataFrame(edge).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(point).drop_duplicates('target_source_record_id').to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(di).to_csv(O/'record_dispositions.csv',index=False);print(len(edge),len(point),len(w));print([(x['name'],x['region'])for x in w])
