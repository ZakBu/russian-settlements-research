"""Historical-only WB code-profile audit. No 2026 survivor conditioning."""
from pathlib import Path
import json,math,csv,itertools,statistics,hashlib
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent;RAW=ROOT/'work/ecommerce_extension_history'
def dist(a,b):
 x,y=a['coordinates'],b['coordinates'];r=math.pi/180
 h=math.sin((y[0]-x[0])*r/2)**2+math.cos(x[0]*r)*math.cos(y[0]*r)*math.sin((y[1]-x[1])*r/2)**2
 return 6371.0088*2*math.asin(math.sqrt(min(1,h)))
def profile(x):return x.get('dtype')==0 and x.get('isWb')is True and x.get('pickupType')in [3,4]
def fitted(x):return (x.get('fittingRooms')or 0)>=1
snap={};summary=[]
expected={x['observation_date']:x['decoded_sha256']for x in json.loads((ROOT/'work/sources/research/ecommerce_settlement_20261024/history_stage_20261024/network/acquisition_manifest.json').read_text())['historical_snapshots']}
for f in sorted(RAW.glob('wb_????-??-??.json')):
 date=f.stem[3:];assert hashlib.sha256(f.read_bytes()).hexdigest()==expected[date];j=json.loads(f.read_bytes());ru=next(x['items']for x in j if x['country']=='ru');d={str(x['id']):x for x in ru};assert len(d)==len(ru)
 snap[date]=d
 summary.append({'observation_date':date,'ru_catalogue_objects':len(d),'raw_code_profile_objects':sum(profile(x)for x in ru),'profile_fitting_positive':sum(profile(x)and fitted(x)for x in ru),'profile_status_missing':sum(profile(x)and x.get('status')is None for x in ru),'profile_positive_fitting_or_unknown':sum(profile(x)and (x.get('fittingRooms')is None or fitted(x))for x in ru)})
pairs=[]
for d0,d1 in itertools.combinations(snap,2):
 a,b=snap[d0],snap[d1];ids=set(a)&set(b);stable={i for i in ids if dist(a[i],b[i])<=.1};pa={i for i in a if profile(a[i])};pb={i for i in b if profile(b[i])}
 pairs.append({'date0':d0,'date1':d1,'common_ids':len(ids),'common_ids_le100m':len(stable),'common_profile_ids':len(pa&pb),'common_profile_ids_le100m':len(pa&pb&stable),'profile0_ids_without_profile1_record':len(pa-pb),'profile1_ids_without_profile0_record':len(pb-pa),'stable_ids_code_profile_true_to_false':sum(profile(a[i])and not profile(b[i])for i in stable),'stable_ids_code_profile_false_to_true':sum(not profile(a[i])and profile(b[i])for i in stable),'stable_profile_ids_fitting_missing_to_positive':sum(profile(a[i])and profile(b[i])and a[i].get('fittingRooms')is None and fitted(b[i])for i in stable),'stable_profile_ids_fitting_positive_to_missing':sum(profile(a[i])and profile(b[i])and fitted(a[i])and b[i].get('fittingRooms')is None for i in stable),'stable_ids_pickupType_changed':sum(a[i].get('pickupType')!=b[i].get('pickupType')for i in stable),'stable_ids_dtype_changed':sum(a[i].get('dtype')!=b[i].get('dtype')for i in stable),'stable_ids_isWb_changed':sum(a[i].get('isWb')!=b[i].get('isWb')for i in stable)})
for name,rows in [('wb_historical_profile.csv',summary),('wb_historical_pairs.csv',pairs)]:
 with (OUT/name).open('w')as f:w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
print(json.dumps(summary,ensure_ascii=False,indent=2));print('FIRST_LAST',json.dumps(pairs[5],ensure_ascii=False,indent=2))
# Optional geography is computed only from restored historical links and joins by date+ID.
links=ROOT/'work/sources/research/ecommerce_settlement_20261024/history_stage_20261024/wb_history_symmetric_links.parquet'
if not links.exists():
 print('GEOGRAPHY_PENDING: restored historical links are not yet available; object audit is complete.');raise SystemExit(0)
import pandas as pd
x=pd.read_parquet(links);x=x.loc[x.archive_date.isin(snap)].copy();x.source_object_id=x.source_object_id.astype(str)
x['raw_profile']=[profile(snap[d][i])for d,i in zip(x.archive_date,x.source_object_id)]
x['raw_profile_fitted']=[profile(snap[d][i])and fitted(snap[d][i])for d,i in zip(x.archive_date,x.source_object_id)]
geo=[]
for radius in [1,5,10]:
 col=f'source_record_id_2021_{radius}km'
 for date,g in x.groupby('archive_date'):
  for kind,flag in [('raw_profile',g.raw_profile),('raw_profile_fitted',g.raw_profile_fitted)]:
   accepted=g.loc[flag&g[col].notna()];geo.append({'observation_date':date,'radius_km':radius,'profile':kind,'positive_nodes':accepted[col].nunique(),'linked_objects':len(accepted),'all_profile_objects':int(flag.sum())})
pd.DataFrame(geo).to_csv(OUT/'wb_historical_profile_geography.csv',index=False)
print('GEOGRAPHY_COMPLETE',len(geo))
