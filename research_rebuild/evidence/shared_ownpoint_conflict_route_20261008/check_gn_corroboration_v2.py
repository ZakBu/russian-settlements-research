from pathlib import Path
import pandas as pd,zipfile,re,unicodedata,math,json
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence/shared_ownpoint_conflict_route_20261008')
d=pd.read_csv(E/'proposed_RCSI_current_point_replacements_not_applied.csv.gz')
def norm(s):return re.sub(r'[^a-zа-я0-9]+',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е')).strip()
def dist(a,b):
 la1,lo1,la2,lo2=map(math.radians,[a[0],a[1],b[0],b[1]]);h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
 return 6371.0088*2*math.asin(math.sqrt(min(1,h)))
bind=pd.read_csv('/workspace/settlements-work/continuation_20261003/geonames_named_point_probe_v1/adm1_literal_alias_bindings.csv',dtype=str)
byregion={norm(r.region_norm):r.admin1 for r in bind.itertuples()}
# Whole populated-place settlement feature codes. PPLH/Q/W retained as rivals but not positive support absent dated current status; PPLX is sublocality and rival-only.
positive={'PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLC','PPLF','PPLG','PPLL','PPLR','PPLS'}
all_ppl=positive|{'PPLH','PPLQ','PPLW','PPLX'}
need={norm(x) for x in d.RCSI_name.unique()}
rows=[]
zipf='/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip'
with zipfile.ZipFile(zipf) as z:
 name='RU.txt'
 for lineno,line in enumerate(z.open(name),1):
  f=line.decode('utf-8').rstrip('\n').split('\t')
  if len(f)<19 or f[6]!='P' or f[7] not in all_ppl:continue
  nm=norm(f[1]); alts={norm(a) for a in f[3].split(',')}; matched=[x for x in need if x==nm or x in alts]
  if not matched:continue
  rows.append({'geonameid':f[0],'name':f[1],'alternatenames':f[3],'lat':float(f[4]),'lon':float(f[5]),'feature_class':f[6],'feature_code':f[7],'country_code':f[8],'admin1':f[10],'source_locator':f'GeoNames RU.txt line {lineno}'})
g=pd.DataFrame(rows); outs=[]
for r in d.itertuples():
 an=byregion.get(norm(r.native_region).replace(' область',''))
 is_name=(g.name.map(norm)==norm(r.RCSI_name))|g.alternatenames.map(lambda a:norm(r.RCSI_name) in {norm(x) for x in a.split(',')})
 cand=g[(g.admin1==an)&is_name].copy();cand['distance_km']=[dist((r.new_latitude,r.new_longitude),(x.lat,x.lon)) for x in cand.itertuples()]
 supported=cand[cand.feature_code.isin(positive)]
 near=supported[supported.distance_km<=1]
 other=cand[~cand.geonameid.isin(near.geonameid)]
 outs.append({'target_source_record_id':r.target_source_record_id,'name':r.RCSI_name,'region':r.native_region,'gn_admin1':an,'same_region_whole_P_candidate_count':len(cand),'eligible_whole_NP_support_count':len(supported),'eligible_within_1km_count':len(near),'nearest_eligible_km':supported.distance_km.min() if len(supported) else None,'near_support_json':json.dumps(near[['geonameid','name','feature_class','feature_code','country_code','admin1','lat','lon','distance_km','source_locator']].to_dict('records'),ensure_ascii=False),'all_other_P_feature_name_rivals_gt5km':bool((other.distance_km>5).all()),'all_P_feature_name_rivals_json':json.dumps(cand[['geonameid','name','feature_class','feature_code','country_code','admin1','lat','lon','distance_km','source_locator']].to_dict('records'),ensure_ascii=False)})
o=pd.DataFrame(outs);o.to_csv(E/'RCSI_GN_corroboration_v2.csv',index=False)
passrows=o[(o.eligible_within_1km_count==1)&o.all_other_P_feature_name_rivals_gt5km]
print('whole P records scanned matching names',len(g),'qualifying',len(passrows),'of',len(o))
print(o[['target_source_record_id','same_region_whole_P_candidate_count','eligible_whole_NP_support_count','eligible_within_1km_count','nearest_eligible_km','all_other_P_feature_name_rivals_gt5km']].to_string(index=False))
