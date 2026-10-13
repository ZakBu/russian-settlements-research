from pathlib import Path
import pandas as pd, zipfile, re, unicodedata, math, json
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence/shared_ownpoint_conflict_route_20261008')
d=pd.read_csv(E/'proposed_RCSI_current_point_replacements_not_applied.csv.gz')
def norm(s):return re.sub(r'[^a-zа-я0-9]+',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е')).strip()
def dist(a,b):
 la1,lo1,la2,lo2=map(math.radians,[a[0],a[1],b[0],b[1]]);h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
 return 6371.0088*2*math.asin(math.sqrt(min(1,h)))
bind=pd.read_csv('/workspace/settlements-work/continuation_20261003/geonames_named_point_probe_v1/adm1_literal_alias_bindings.csv',dtype=str)
byregion={norm(r.region_norm):r.admin1 for r in bind.itertuples()}
need={norm(x):x for x in d.RCSI_name.unique()}; regs={norm(x):x for x in d.native_region.unique()}
zipf='/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip'
rows=[]
with zipfile.ZipFile(zipf) as z:
 name=next(x for x in z.namelist() if x.endswith('/RU.txt') or x=='RU.txt')
 for line in z.open(name):
  f=line.decode('utf-8').rstrip('\n').split('\t')
  if len(f)<19 or f[7] not in ('P','PPL'):continue
  nm=norm(f[1]); alts={norm(a) for a in f[3].split(',')}; matched=[x for x in need if x==nm or x in alts]
  if not matched:continue
  rows.append({'geonameid':f[0],'name':f[1],'alternatenames':f[3],'feature_class':f[7],'feature_code':f[8],'lat':float(f[4]),'lon':float(f[5]),'admin1':f[10]})
g=pd.DataFrame(rows)
outs=[]
for r in d.itertuples():
 rn=norm(r.native_region).replace(' область',''); an=byregion.get(rn)
 cand=g[(g.admin1==an)&((g.name.map(norm)==norm(r.RCSI_name))|g.alternatenames.map(lambda a:norm(r.RCSI_name) in {norm(x) for x in a.split(',')}))].copy()
 ds=[dist((r.new_latitude,r.new_longitude),(x.lat,x.lon)) for x in cand.itertuples()]
 cand['distance_km']=ds
 near=cand[cand.distance_km<=1]
 outs.append({'target_source_record_id':r.target_source_record_id,'name':r.RCSI_name,'region':r.native_region,'gn_admin1':an,'same_region_exactname_PPL_count':len(cand),'within_1km':len(near),'nearest_km':min(ds,default=None),'near_ids':','.join(near.geonameid.astype(str)),'all_candidates_gt5km_except_near':bool((cand.distance_km.gt(5)|cand.distance_km.le(1)).all())})
o=pd.DataFrame(outs);o.to_csv(E/'RCSI_GN_corroboration.csv',index=False)
print(o.groupby(['within_1km','all_candidates_gt5km_except_near']).size().to_dict())
print('rows qualify',int(((o.within_1km==1)&o.all_candidates_gt5km_except_near).sum()),'/',len(o))
print(o[(o.within_1km!=1)|(~o.all_candidates_gt5km_except_near)].to_string(index=False))
