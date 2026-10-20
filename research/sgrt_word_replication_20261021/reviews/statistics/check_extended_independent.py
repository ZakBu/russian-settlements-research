#!/usr/bin/env python3
from pathlib import Path
import numpy as np,pandas as pd,json,hashlib,time
from sklearn.neighbors import BallTree
BASE=Path(__file__).resolve().parents[2];OLD=BASE.parent/'sgrt_national_integration_20261019';OUT=BASE/'reviews/statistics';checks=[];t=time.monotonic()
def ck(name,ok,**info):checks.append({'check':name,'pass':bool(ok),**info})
m=pd.read_parquet(BASE/'results/memberships.parquet').set_index('id')
e=pd.read_csv(BASE/'education/validation_external_edges.csv');e=e[e.origin_uid.isin(m.index)&e.destination_uid.isin(m.index)]
actual=pd.read_csv(BASE/'results/documented_education_model_comparison.csv')
ck('98_external_canonical_dated_assertions',len(e)==98 and len(actual)==98)
ck('77_unique_pairs_74_origins_16providers',len(e[['origin_uid','destination_uid']].drop_duplicates())==77 and e.origin_uid.nunique()==74 and e.destination_uid.nunique()==16)
mp=e.origin_uid.map(m.center_id_l1);ed=e.origin_uid.map(m.education_potential_provider_id)
ck('multifunction_postdevelopment_exact2of98',int(mp.eq(e.destination_uid).sum())==2)
ck('education_postdevelopment_exact0of98',int(ed.eq(e.destination_uid).sum())==0)
providers=e.destination_uid.unique();positive=int(m.loc[providers,'candidate_center'].sum())
ck('documented_providers_candidate3of16',positive==3,n_candidate_providers=positive)
ck('17of98_assertions_have_candidateprovider',int(e.destination_uid.map(m.candidate_center).sum())==17)
ck('not_blind_holdout_marked',actual.filter(regex='blind').size>0 or 'post-development' in json.load(open(BASE/'results/extended_check_receipt.json'))['documented_education']['scope'])
# Independently derive own source counts without importing author functions.
d=pd.read_parquet(OLD/'core/feature_master.parquet');commerce=pd.read_parquet(BASE/'commerce/settlement_features.parquet')
ck('fresh_commerce_axis_matches',commerce.id.equals(d.id))
legal={'trade_access':'retail47','food_service':'food56','education':'education85','healthcare':'health86','social_care':'social8788','repair':'repair95','personal':'personal96'}
phys={'trade_access':['retail_store','market'],'food_service':['food_service'],'education':['school','preschool','other_education'],'healthcare':['hospital','healthcare'],'veterinary':['veterinary'],'pharmacy':['pharmacy'],'banking':['bank','atm'],'postal_service':['post_office','postal_collection_point']}
groups=['trade_access','food_service','education','healthcare','social_care','repair','personal','veterinary','pharmacy','banking','postal_service']
counts=[]
for g in groups:
 l=d[f'econ_native_2025_{legal[g]}_legal_entities'].values if g in legal else np.zeros(len(d))
 p=sum((d[f'places_baseline_{cat}_count'].values for cat in phys.get(g,[])),start=np.zeros(len(d)))
 if g=='trade_access':p=np.fmax(p,d.wb_strict_focus_types_locations.values)
 counts.append(np.fmax(l,p))
basecounts=np.column_stack(counts);freshcounts=basecounts.copy()
freshcounts[:,0]=np.maximum.reduce([d.econ_native_2025_retail47_legal_entities.values,(d.places_baseline_retail_store_count+d.places_baseline_market_count).values,commerce.commerce_wb20261021_baseline_focus_count.values])
coords=np.deg2rad(d[['lat','lon']].values);anchors=d.places_baseline_school_count.gt(0).values|d.places_baseline_hospital_count.gt(0).values
assignment=[]
for mode,c in [('frozen',basecounts),('fresh',freshcounts)]:
 log=np.log1p(c)
 for j in range(log.shape[1]):
  pos=log[:,j][log[:,j]>0]
  if len(pos):log[:,j]=np.minimum(log[:,j],np.percentile(pos,99))
 mass=log.sum(axis=1);candidate=(c>0).sum(axis=1)>=2;candidate|=anchors;ci=np.flatnonzero(candidate)
 tree=BallTree(coords[ci],metric='haversine');chosen=np.full(len(d),-1,int)
 for start in range(0,len(d),4096):
  inds,dists=tree.query_radius(coords[start:start+4096],r=75/6371.0088,return_distance=True)
  for offset,(ix,dist) in enumerate(zip(inds,dists)):
   i=start+offset
   if candidate[i]:chosen[i]=i;continue
   if not len(ix):continue
   ii=ci[ix];weights=mass[ii]*np.exp(-(dist*6371.0088)/15)
   chosen[i]=ii[np.lexsort((ii,-weights))[0]]
 assignment.append(chosen)
 ck(mode+'_ordinary_allaxis_assignments_recomputed',len(chosen)==142570)
frozen,fresh=assignment;saved=pd.read_parquet(BASE/'results/fresh_wb_membership_sensitivity.parquet')
ids=d.id.values;frozenids=np.where(frozen>=0,ids[np.maximum(frozen,0)],'UNASSIGNED');freshids=np.where(fresh>=0,ids[np.maximum(fresh,0)],'UNASSIGNED')
ck('frozen_ordinary_allaxis_BallTree_winners',np.array_equal(frozenids,saved.frozen_ordinary_center_id.fillna('UNASSIGNED').values))
ck('fresh_ordinary_allaxis_BallTree_winners',np.array_equal(freshids,saved.fresh_wb_ordinary_center_id.fillna('UNASSIGNED').values))
ck('fresh_WB_exact6_changed',int((frozen!=fresh).sum())==6,n_changed=int((frozen!=fresh).sum()))
ck('fresh_WB_saved_changed_flags_exact',np.array_equal(saved.changed.values,frozen!=fresh))
ck('fresh_WB_no_federal_comparison',not any(str(u).startswith('RU-FED') for u in saved.frozen_ordinary_center_id.dropna()))
report={'status':'PASS_POSTDEVELOPMENT_AND_CATALOG_SENSITIVITY' if all(c['pass'] for c in checks) else 'REVISE','checks':checks,'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'independent_method':'No author model import. All142570 ordinary assignments for frozen/fresh catalogs independently computed using BallTreehaversine and explicit weights, distinct from author cKDTree/chord implementation. Documentary labels recomputed by UID joins.','scientific_interpretation':'2/98 multidisciplinary model matches and0/98educationmatches indicate poor source/functional agreement on this disclosed local corpus, not calibrated national accuracy. Only3/16knownproviders are modelcandidates. These are post-development comparisons and not blindholdout. Six WBcatalog-derived assignment changes are sensitivity tocatalogsnapshot, not realworldclosure.','seconds':round(time.monotonic()-t,3),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(OUT/'independent_extended_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps({'status':report['status'],'n_checks':len(checks),'n_failed':report['n_failed'],'seconds':report['seconds']},ensure_ascii=False))
