from pathlib import Path
import pandas as pd, numpy as np, duckdb, zipfile, json, re, hashlib, unicodedata, math, collections
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence/shared_ownpoint_conflict_route_20261008')
H=Path('/workspace/russian-settlements-research/research_rebuild/evidence/grounded_current_carrier_expansion_20261008/admission_holds.csv.gz')
P=Path('/workspace/russian-settlements-research/research_rebuild/evidence/main_axis_residual_application63_20261008/applied_point_snapshot.parquet')
NATIVE=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
RCSI=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/rcsi_github_settlements.csv')
OSM=Path('/workspace/settlements-work/coordinate_first_20261008/sources/osm_geoapify_ru.zip')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def norm(s):
 if s is None or pd.isna(s):return ''
 return re.sub(r'[^a-zа-я0-9]+',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е')).strip()
def typed(x):
 s=str(x).strip().split(None,1); return (norm(s[0]) if s else '',norm(s[1]) if len(s)>1 else '')
def type_key(x):
 v=norm(x);return {'д':'деревня','дер':'деревня','деревня':'деревня','п':'поселок','поселок':'поселок','с':'село','село':'село','пгт':'пгт','поселок городского типа':'пгт','г':'город','город':'город'}.get(v,v)
def admin_key(x):
 v=norm(x)
 for w in ['муниципальный район','муниципальная район','муниципальный округ','городской округ','городской район','муниципальное образование','сельское поселение','городское поселение','район','округ','сельсовет']:
  v=v.replace(norm(w),' ')
 return ' '.join(v.split())
def distkm(a,b):
 la1,lo1,la2,lo2=map(math.radians,[a[0],a[1],b[0],b[1]])
 h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
 return 6371.0088*2*math.asin(math.sqrt(min(1,h)))

def main():
 h=pd.read_csv(H); h=h[h.held_reason.eq('accepted ownpoint shared by separate same-year native record')].copy()
 assert len(h)==254
 con=duckdb.connect(); native=con.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,municipality_raw,oktmo,okato,source_file,source_row,population from read_parquet(?) where census_year=2021',[str(NATIVE)]).fetchdf()
 p=pd.read_parquet(P,columns=['target_source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_origin_ledger','coordinate_origin_ledger_sha256'])
 p=p.merge(native[['source_record_id','census_year']],left_on='target_source_record_id',right_on='source_record_id',how='inner',validate='many_to_one');p=p[p.census_year.eq(2021)].copy();p['lat7']=pd.to_numeric(p.latitude).round(7);p['lon7']=pd.to_numeric(p.longitude).round(7)
 groups={(la,lo):g for (la,lo),g in p.groupby(['lat7','lon7']) if len(g)>1}
 pbyid=p.set_index('target_source_record_id',drop=False)
 pairs=[]; members=set()
 for _,r in h.iterrows():
  q=pbyid.loc[r.to_source_record_id]
  assert isinstance(q,pd.Series), (r.to_source_record_id,type(q))
  g=groups[(q.lat7,q.lon7)];members.update(g.target_source_record_id)
  pairs.append({'old_source_record_id':r.from_source_record_id,'current_source_record_id':r.to_source_record_id,'old_year':int(r.from_year),'old_population':int(r.from_population),'current_population':int(r.to_population),'name':r['name'],'old_point_coordinate':f'{q.latitude},{q.longitude}','collision_group_size':len(g),'shared_coordinate_source_kind':q.point_origin_kind,'shared_coordinate_source_record_ids_json':json.dumps(sorted(g.target_source_record_id.astype(str)),ensure_ascii=False)})
 pairs=pd.DataFrame(pairs)
 members=sorted(members); rownum=pd.Series(members).str.rsplit(':',n=1).str[-1].astype(int)-1
 raw=pd.read_parquet(RAW,columns=['object_name','oktmo','region','mun_upper','mun_lower','settlement_type_dadata','object_level','latitude_dadata','longitude_dadata','settlement_dadata','settlement_type_full_dadata','fias_id_dadata','fias_level_dadata'])
 n=raw.iloc[rownum.to_numpy()].copy().reset_index(drop=True);n['source_record_id']=members
 n[['native_type_prefix','native_name']]=n.object_name.apply(lambda x:pd.Series(typed(x)))
 n['native_type_key']=n.native_type_prefix.map(type_key);n['native_name_key']=n.native_name.map(norm);n['code']=n.oktmo.fillna('').astype(str).str.replace(r'\.0$','',regex=True)
 # RCSI route: exact native OKTMO; one full-code row; exact native name/type, region, and upper municipality.
 rr=pd.read_csv(RCSI,sep=';',dtype=str);rr['code']=rr.oktmo.fillna('').astype(str).str.replace(r'\.0$','',regex=True);rr['name_key']=rr.settlement.map(norm);rr['type_key']=rr.type.map(type_key);rr['region_key']=rr.region.map(norm);rr['upper_admin_key']=rr.municipality.map(admin_key);rr['lat']=pd.to_numeric(rr.latitude_dd,errors='coerce');rr['lon']=pd.to_numeric(rr.longitude_dd,errors='coerce')
 rcode={c:g for c,g in rr.groupby('code')}
 rrecords=[]
 for _,z in n.iterrows():
  g=rcode.get(z.code)
  if g is None: mg=rr.iloc[0:0]
  else: mg=g[(g.name_key==z.native_name_key)&(g.type_key==z.native_type_key)&(g.region_key==norm(z.region))&(g.upper_admin_key==admin_key(z.mun_upper))]
  rrecords.append({'source_record_id':z.source_record_id,'strict_rcsi_match_count':len(mg),'rcsi_records':mg[['id','settlement','type','region','municipality','latitude_dd','longitude_dd','oktmo']].to_dict('records')})
 rmap=pd.DataFrame(rrecords).set_index('source_record_id')
 # Cached OSM exact-name physical candidate index for this bounded 264-member set.
 wanted=set(n.native_name_key); osmrows=[]
 with zipfile.ZipFile(OSM) as z:
  for fn in ['ru/place-hamlet.ndjson','ru/place-village.ndjson','ru/place-town.ndjson','ru/place_city.ndjson']:
   print('scanning_osm',fn,flush=True)
   if fn not in z.namelist():continue
   with z.open(fn) as f:
    for li,line in enumerate(f,1):
     try:o=json.loads(line)
     except Exception:continue
     nk=norm(o.get('name',''))
     if nk not in wanted:continue
     a=o.get('address') or {};loc=o.get('location')
     if not isinstance(loc,list) or len(loc)<2:continue
     osmrows.append({'name_key':nk,'name':o.get('name'),'feature':o.get('type'),'osm_type':o.get('osm_type'),'osm_id':str(o.get('osm_id')),'member':fn,'line':li,'lat':float(loc[1]),'lon':float(loc[0]),'state':a.get('state',''),'county':a.get('county',''),'municipality':a.get('municipality',''),'village':a.get('village',''),'town':a.get('town',''),'city':a.get('city',''),'hamlet':a.get('hamlet',''),'display_name':o.get('display_name','')})
 O=pd.DataFrame(osmrows); O['region_key']=O.state.map(norm);O['county_key']=O.county.map(admin_key);O['mun_key']=O.municipality.map(admin_key)
 # Build full-source exact-name/native county competitors to make ambiguity explicit.
 allraw=pd.read_parquet(RAW,columns=['object_name','region','mun_upper','mun_lower','oktmo','object_level']); allraw=allraw[allraw.object_level.eq('Населенный пункт')].copy();allraw[['type_prefix','name_key']]=allraw.object_name.apply(lambda x:pd.Series(typed(x)));allraw['region_key']=allraw.region.map(norm);allraw['upper_key']=allraw.mun_upper.map(admin_key);allraw['lower_key']=allraw.mun_lower.map(admin_key)
 osm_for=[]
 for _,z in n.iterrows():
  native_comp=allraw[(allraw.name_key==z.native_name_key)&(allraw.region_key==norm(z.region))&(allraw.upper_key==admin_key(z.mun_upper))]
  cand=O[(O.name_key==z.native_name_key)&(O.region_key==norm(z.region))&(O.county_key==admin_key(z.mun_upper))]
  exactmun=cand[cand.mun_key.eq(admin_key(z.mun_lower))] if admin_key(z.mun_lower) else cand.iloc[0:0]
  # Fully code-like binding available only if native label is unique in upper-county, or OSM municipality resolves it.
  route_candidates=exactmun if len(native_comp)>1 else cand
  osm_for.append({'source_record_id':z.source_record_id,'native_same_name_same_upper_admin_count_full2021':len(native_comp),'osm_exact_name_region_county_candidate_count':len(cand),'osm_exact_lower_municipality_candidate_count':len(exactmun),'osm_route_candidate_count':len(route_candidates),'osm_candidate_records':route_candidates[['osm_id','feature','member','line','lat','lon','county','municipality','display_name']].to_dict('records')})
 omap=pd.DataFrame(osm_for).set_index('source_record_id')
 # Evaluate full collision groups; replacements only possible where every member has one independently unique positive route and noncolliding coordinates.
 group_rows=[]
 held_targets=set(pairs.current_source_record_id.astype(str))
 for (la,lo),g in groups.items():
  mids=list(g.target_source_record_id.astype(str))
  if not (held_targets & set(mids)):continue
  mm=n[n.source_record_id.isin(mids)]
  routes=[];coord=[]
  for sid in mids:
   rc=rmap.loc[sid];oc=omap.loc[sid]
   if int(rc.strict_rcsi_match_count)==1:
    obj=rc.rcsi_records[0];routes.append(('RCSI',sid));coord.append((float(obj['latitude_dd']),float(obj['longitude_dd'])))
   elif int(oc.osm_route_candidate_count)==1:
    obj=oc.osm_candidate_records[0];routes.append(('OSM',sid));coord.append((float(obj['lat']),float(obj['lon'])))
   else: routes.append(('',sid));coord.append(None)
  allbound=all(k for k,_ in routes)
  minsep=0.0
  if allbound:
   ds=[distkm(coord[i],coord[j]) for i in range(len(coord)) for j in range(i)]
   minsep=min(ds,default=999.0)
  heldpairs=int(pairs.current_source_record_id.isin(mids).sum())
  oldpop=int(pairs[pairs.current_source_record_id.isin(mids)].old_population.sum())
  group_rows.append({'lat':la,'lon':lo,'group_size':len(mids),'held_pair_count':heldpairs,'held_old_population':oldpop,'members_json':json.dumps(mids,ensure_ascii=False),'routes_json':json.dumps(routes,ensure_ascii=False),'all_members_independently_sourcebound_cached_point':allbound,'minimum_member_coordinate_separation_km':minsep,'group_mass_correction_candidate':bool(allbound and minsep>0.1)})
 groupsdf=pd.DataFrame(group_rows)
 pairs=pairs.merge(n[['source_record_id','native_name','native_type_key','region','mun_upper','mun_lower','oktmo','object_level']],left_on='current_source_record_id',right_on='source_record_id',how='left').drop(columns=['source_record_id'])
 pairs=pairs.merge(rmap.reset_index(),left_on='current_source_record_id',right_on='source_record_id',how='left').drop(columns=['source_record_id'])
 pairs=pairs.merge(omap.reset_index(),left_on='current_source_record_id',right_on='source_record_id',how='left').drop(columns=['source_record_id'])
 pairs.to_csv(E/'held_254_pair_diagnostics.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 groupsdf.to_csv(E/'collision_groups_diagnostics.csv',index=False)
 print({'pairs':len(pairs),'member_source_rows':len(n),'point_collision_groups':len(groupsdf),'held_old_population':int(pairs.old_population.sum()),'held_current_population_context':int(pairs.current_population.sum()),'old_year_counts':pairs.old_year.value_counts().to_dict(),'RCSI_unique_strict_members':int((rmap.strict_rcsi_match_count==1).sum()),'OSM_exact_name_county_unique_member_routes':int((omap.osm_route_candidate_count==1).sum()),'full_groups_all_members_have_unique_independent_cached_point':int(groupsdf.all_members_independently_sourcebound_cached_point.sum()),'group_candidates_separated_gt100m':int(groupsdf.group_mass_correction_candidate.sum()),'candidate_oldpop':int(groupsdf.loc[groupsdf.group_mass_correction_candidate,'held_old_population'].sum())})
 for k in ['point_inputs','source_hashes']:pass
 pins={str(q):{'sha256':sha(q),'bytes':q.stat().st_size} for q in [H,P,NATIVE,RAW,RCSI,OSM]}
 receipt={'status':'bounded_shared_ownpoint_conflict_diagnosis_only_not_applied','holds_path':str(H),'holds_sha256':pins[str(H)]['sha256'],'held_pairs':len(pairs),'old_pop':int(pairs.old_population.sum()),'point_collision_groups':len(groupsdf),'group_candidate_rule':'all current same-year members in a collision group need either one exact-code/name/type/region/upper-municipality RCSI source row or a unique exact-name/region/county OSM physical-place object, with resulting candidate points separated >100m; no group currently passes','source_pins':pins,'outputs':{}}
 for q in [E/'held_254_pair_diagnostics.csv.gz',E/'collision_groups_diagnostics.csv']:
  receipt['outputs'][q.name]={'sha256':sha(q),'bytes':q.stat().st_size}
 (E/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
