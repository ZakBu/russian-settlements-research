from pathlib import Path
import pandas as pd, json, re, unicodedata, hashlib, math
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence/shared_ownpoint_conflict_route_20261008')
PAIR=E/'held_254_pair_diagnostics.csv.gz'; P=Path('/workspace/russian-settlements-research/research_rebuild/evidence/main_axis_residual_application63_20261008/applied_point_snapshot.parquet'); NAT=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'); RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'); RCSI=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/rcsi_github_settlements.csv')
def norm(s):
 if s is None or pd.isna(s): return ''
 return re.sub(r'[^a-zа-я0-9]+',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е')).strip()
def admin(s):
 v=norm(s)
 for q in ['муниципальный район','муниципальный округ','городской округ','городской район','район','округ']:
  v=v.replace(norm(q),' ')
 return ' '.join(v.split())
def typ(s):return {'д':'деревня','дер':'деревня','деревня':'деревня','п':'поселок','поселок':'поселок','с':'село','село':'село','пгт':'пгт','поселок городского типа':'пгт'}.get(norm(s),norm(s))
def dist(a,b):
 la1,lo1,la2,lo2=map(math.radians,[a[0],a[1],b[0],b[1]]);h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
 return 6371.0088*2*math.asin(math.sqrt(min(1,h)))
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def main():
 pairs=pd.read_csv(PAIR);points=pd.read_parquet(P,columns=['target_source_record_id','latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_source_record_id','coordinate_admission_status'])
 nat=pd.read_parquet(NAT,columns=['source_record_id','census_year','settlement_name','settlement_type','region_norm','district_raw','oktmo','population']);nat=nat[nat.census_year.eq(2021)]
 raw=pd.read_parquet(RAW,columns=['object_name','oktmo','region','mun_upper','mun_lower','object_level']);raw=raw.reset_index(drop=True)
 ids=sorted(set(sum((json.loads(s) for s in pairs.shared_coordinate_source_record_ids_json),[])))
 r=pd.DataFrame({'source_record_id':ids});r['raw_row']=r.source_record_id.str.rsplit(':',n=1).str[-1].astype(int); n=raw.iloc[r.raw_row.to_numpy()-1].reset_index(drop=True); n['source_record_id']=ids
 def parse(label):
  bits=str(label).split(None,1); return (typ(bits[0]) if bits else '',norm(bits[1]) if len(bits)>1 else '')
 n[['native_type_key','native_name_key']]=n.object_name.apply(lambda x:pd.Series(parse(x)))
 n['code']=n.oktmo.fillna('').astype(str).str.replace(r'\.0$','',regex=True);n['region_key']=n.region.map(norm);n['upper_key']=n.mun_upper.map(admin)
 rr=pd.read_csv(RCSI,sep=';',dtype=str);rr['code']=rr.oktmo.fillna('').astype(str).str.replace(r'\.0$','',regex=True);rr['name_key']=rr.settlement.map(norm);rr['type_key']=rr.type.map(typ);rr['region_key']=rr.region.map(norm);rr['upper_key']=rr.municipality.map(admin);rr['lat']=pd.to_numeric(rr.latitude_dd,errors='coerce');rr['lon']=pd.to_numeric(rr.longitude_dd,errors='coerce')
 bycode={c:g for c,g in rr.groupby('code')}; rm={}
 for z in n.itertuples(index=False):
  g=bycode.get(z.code)
  if g is None: m=rr.iloc[0:0]
  else:m=g[(g.name_key==z.native_name_key)&(g.type_key==z.native_type_key)&(g.region_key==z.region_key)&(g.upper_key==z.upper_key)]
  rm[z.source_record_id]=m
 assert sum(len(v)==1 for v in rm.values())==107
 # active current-year point index and all coordinates, to screen collisions after corrections.
 pp=points.merge(nat[['source_record_id','census_year']],left_on='target_source_record_id',right_on='source_record_id',how='inner',validate='many_to_one');pp=pp[pp.census_year.eq(2021)].copy();pp['key']=list(zip(pd.to_numeric(pp.latitude).round(7),pd.to_numeric(pp.longitude).round(7)));
 native_byid=n.set_index('source_record_id').to_dict('index')
 rcsi_sha=sha(RCSI)
 # Reconstruct 123 Dadata duplicate groups.
 groupmap={}
 for _,z in pairs.iterrows():
  members=tuple(sorted(json.loads(z.shared_coordinate_source_record_ids_json)));groupmap[members]=None
 # choose candidates per full duplicate group; leave one record on Dadata if exactly one lacks unique RCSI, otherwise stable first ID is retained.
 replacements=[];groupout=[];routepop=0;routepairs=0
 for members in sorted(groupmap):
  available=[sid for sid in members if len(rm[sid])==1]
  missing=[sid for sid in members if len(rm[sid])!=1]
  if len(missing)>1 or len(available)<len(members)-1:
   groupout.append({'members_json':json.dumps(members,ensure_ascii=False),'group_size':len(members),'unique_RCSI_members':len(available),'unresolved_members':len(missing),'group_status':'HOLD_insufficient_unique_code_bound_RCSI_points','proposal_rows':0,'held_pair_count':int(pairs.current_source_record_id.isin(members).sum()),'held_old_population':int(pairs[pairs.current_source_record_id.isin(members)].old_population.sum())});continue
  anchor=missing[0] if missing else members[0]
  candidate_coords=[];local=[]
  valid=True
  for sid in members:
   if sid==anchor:continue
   m=rm[sid]; row=m.iloc[0]
   if pd.isna(row.lat) or pd.isna(row.lon) or not(-90<=row.lat<=90 and -180<=row.lon<=180):valid=False;break
   local.append((sid,row));candidate_coords.append((float(row.lat),float(row.lon)))
  # all final points in the group must be spatially separated by >100m; raw Dadata anchor remains original.
  oldcoord=pp[pp.target_source_record_id.eq(anchor)]
  if len(oldcoord)!=1: valid=False; old=(0,0)
  else: old=(float(oldcoord.iloc[0].latitude),float(oldcoord.iloc[0].longitude))
  final_coords=candidate_coords+[old]
  if valid and min((dist(final_coords[i],final_coords[j]) for i in range(len(final_coords)) for j in range(i)),default=999)<=0.1:valid=False
  # Updated RCSI candidates must not hit an out-of-group active 2021 source point.
  outside=set(pp.target_source_record_id)-set(members)
  for sid,row in local:
   key=(round(float(row.lat),7),round(float(row.lon),7))
   occ=pp[(pp.key.apply(lambda k:k==key)) & pp.target_source_record_id.isin(outside)]
   if len(occ):valid=False
  if not valid:
   groupout.append({'members_json':json.dumps(members,ensure_ascii=False),'group_size':len(members),'unique_RCSI_members':len(available),'unresolved_members':len(missing),'group_status':'HOLD_candidate_point_collision_or_too_close','proposal_rows':0,'held_pair_count':int(pairs.current_source_record_id.isin(members).sum()),'held_old_population':int(pairs[pairs.current_source_record_id.isin(members)].old_population.sum())});continue
  pairg=pairs[pairs.current_source_record_id.isin(members)];routepairs+=len(pairg);routepop+=int(pairg.old_population.sum())
  for sid,row in local:
   old=pp[pp.target_source_record_id.eq(sid)].iloc[0]
   replacements.append({'target_source_record_id':sid,'replacement_status':'candidate_current_RCSI_ownpoint_replacement_only_not_applied','old_latitude':float(old.latitude),'old_longitude':float(old.longitude),'new_latitude':float(row.lat),'new_longitude':float(row.lon),'distance_old_to_new_km':dist((float(old.latitude),float(old.longitude)),(float(row.lat),float(row.lon))),'point_origin_file':str(RCSI),'point_origin_sha256':rcsi_sha,'point_origin_locator':f'RCSI row id={row.id}; one-based CSV data row={int(row.name)+2}; oktmo={row.oktmo}','point_origin_kind':'RCSI_literal_physical_settlement_exact_current_OKTMO_name_type_region_municipality','native_source_record_id':sid,'native_OKTMO':str(native_byid[sid]['code']),'native_name':str(native_byid[sid]['object_name']),'native_type':str(native_byid[sid]['object_name']).split(None,1)[0],'native_region':str(row.region),'RCSI_municipality':str(row.municipality),'RCSI_name':str(row.settlement),'RCSI_type':str(row.type),'RCSI_record_id':str(row.id),'coordinate_admission_status':'proposal_only_requires_root_review'})
  groupout.append({'members_json':json.dumps(members,ensure_ascii=False),'group_size':len(members),'unique_RCSI_members':len(available),'unresolved_members':len(missing),'group_status':'CANDIDATE_all_but_one_replaced_by_unique_RCSI_point_and_no_residual_point_collision','proposal_rows':len(local),'held_pair_count':len(pairg),'held_old_population':int(pairg.old_population.sum()),'anchor_kept_on_original_Dadata_point':anchor,'minimum_final_group_separation_km':min(dist(final_coords[i],final_coords[j]) for i in range(len(final_coords)) for j in range(i))})
 rep=pd.DataFrame(replacements); groups=pd.DataFrame(groupout)
 rep.to_csv(E/'proposed_RCSI_current_point_replacements_not_applied.csv.gz',index=False,compression={'method':'gzip','mtime':0});groups.to_csv(E/'RCSI_group_route_summary.csv',index=False)
 print({'held_pairs':len(pairs),'held_old_population':int(pairs.old_population.sum()),'duplicate_groups':len(groupout),'groups_candidate':int(groups.group_status.str.startswith('CANDIDATE').sum()),'candidate_replacements':len(rep),'candidate_held_pairs':routepairs,'candidate_old_population':routepop,'held_groups':int(groups.group_status.str.startswith('HOLD').sum())})
if __name__=='__main__':main()
