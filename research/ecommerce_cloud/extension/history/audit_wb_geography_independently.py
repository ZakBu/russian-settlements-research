"""Independent named-candidate/Haversine verification of all historical WB links.
Does not import the production KD-tree linker or depend on its candidate list.
"""
from pathlib import Path
import json,re,unicodedata,math,collections,itertools,csv,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent;BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024';RAW=ROOT/'work/ecommerce_extension_history';KEY='source_record_id_2021'
def clean(x):
 return re.sub(r'\s+',' ',re.sub(r'[^\w\s-]',' ',unicodedata.normalize('NFKC',str(x)).lower().replace('ё','е'))).strip()
prefix=re.compile(r'^(?:город|г\.?|село|с\.?|деревня|д\.?|хутор|х\.?|станица|ст-ца|поселок городского типа|рабочий поселок|пгт\.?|р\.?\s*п\.?|поселок|пос\.?|п\.?|аул|слобода|сл\.?|станция|ст\.?)\s+',re.I)
def names(addr):return {clean(prefix.sub('',re.sub(r'\([^)]*\)',' ',p).strip()))for p in addr.lower().replace('ё','е').split(',')[:4]}
def distance(a,b,c,d):
 r=math.pi/180;h=math.sin((c-a)*r/2)**2+math.cos(a*r)*math.cos(c*r)*math.sin((d-b)*r/2)**2
 return 6371.0088*2*math.asin(math.sqrt(min(1,h)))
def profile(x):return x.get('dtype')==0 and x.get('isWb')is True and x.get('pickupType')in [3,4]
target=pd.read_parquet(BASE/'national/national_target_source2021.parquet');assert len(target)==144151
index=collections.defaultdict(list)
for row in target.loc[target.accepted_point_present_2021].itertuples(index=False):index[clean(row.name_2021)].append((getattr(row,KEY),row.accepted_latitude_2021,row.accepted_longitude_2021))
links=pd.read_parquet(BASE/'history_stage_20261024/wb_history_symmetric_links.parquet');links=links.loc[links.archive_date.ne('2026-10-21')].copy();links.source_object_id=links.source_object_id.astype(str);look=links.set_index(['archive_date','source_object_id'])
independent={};profile_sets={};fitted_sets={};checked=0
for f in sorted(RAW.glob('wb_????-??-??.json')):
 date=f.stem[3:];ru=next(x['items']for x in json.loads(f.read_bytes())if x['country']=='ru');independent[date]={r:set()for r in [1,5,10]};profile_sets[date]={r:set()for r in [1,5,10]};fitted_sets[date]={r:set()for r in [1,5,10]}
 for x in ru:
  n=names(x['address']);lat,lon=x['coordinates'];candidates=[]
  for name in n:
   for sid,a,b in index.get(name,[]):
    # A latitude difference is a safe broad rejection before Haversine.
    if abs(lat-a)>.1:continue
    km=distance(lat,lon,a,b)
    if km<=10:candidates.append((sid,km))
  observed=look.loc[(date,str(x['id']))]
  for radius in [1,5,10]:
   matches=[p for p in candidates if p[1]<=radius];sid=matches[0][0]if len(matches)==1 else None;given=observed[f'{KEY}_{radius}km'];given=None if pd.isna(given)else given
   assert sid==given,(date,x['id'],radius,sid,given)
   checked+=1
   if sid is not None:
    independent[date][radius].add(sid)
    if profile(x):
     profile_sets[date][radius].add(sid)
     if (x.get('fittingRooms')or 0)>=1:fitted_sets[date][radius].add(sid)
ctx=pd.read_parquet(BASE/'history_stage_20261024/centres/settlement_admin_context_main2021.parquet');ctx=ctx.set_index(KEY)
allcentres=set(ctx.index[ctx.admin_centre_positive_20211103]);known=set(ctx.index[ctx.context_status_20211103.eq('accepted_administrative_parent_and_centre')]);pop=target.set_index(KEY).population_2002
systems=pd.read_csv(BASE/'settlement_role_stage_20261024/system/centre_system_demography.csv')
medium=set(systems.loc[systems.medium_primary2002,KEY]);assert len(medium)==1273
def classify(ids):return {'documented_centres2021':len(ids&allcentres),'medium_primary2020_centres_population2002_5to50k':len(ids&medium),'other_known_context_members2021':len((ids&known)-allcentres),'unknown_context_noncentres':len(ids-known-allcentres)}
geo=[]
for date in independent:
 for radius in [1,5,10]:
  for kind,sets in [('raw_code_profile',profile_sets),('raw_code_profile_fitted',fitted_sets)]:
   ids=sets[date][radius];geo.append(dict(observation_date=date,radius_km=radius,profile=kind,positive_nodes=len(ids),**classify(ids)))
pairs=[]
for d0,d1 in itertools.combinations(independent,2):
 for radius in [1,5,10]:
  a,b=profile_sets[d0][radius],profile_sets[d1][radius]
  for contrast,ids in [('later_profile_without_earlier_profile',b-a),('later_profile_without_earlier_any_catalogue',b-independent[d0][radius]),('earlier_profile_without_later_profile',a-b),('profile_positive_both_dates',a&b)]:
   pairs.append(dict(date0=d0,date1=d1,radius_km=radius,contrast=contrast,positive_nodes=len(ids),**classify(ids)))
for name,rows in [('wb_profile_admin_geography.csv',geo),('wb_profile_geographic_contrasts.csv',pairs)]:
 with (OUT/name).open('w')as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
expected=pd.read_csv(OUT/'wb_historical_profile_geography.csv');actual=pd.DataFrame(geo)
for x in expected.itertuples(index=False):
 kind='raw_code_profile'if x.profile=='raw_profile'else 'raw_code_profile_fitted';z=actual.loc[actual.observation_date.eq(x.observation_date)&actual.radius_km.eq(x.radius_km)&actual.profile.eq(kind)].iloc[0];assert x.positive_nodes==z.positive_nodes
summary={'independent_object_radius_checks':checked,'mismatches':0,'geography_rows_verified':len(geo),'method':'normalized-name inverted candidate index plus Haversine; no KD-tree or production candidate list','snapshots':len(independent),'historical_objects':len(links),'documented_centres2021_denominator':len(allcentres),'medium_centres_denominator':len(medium),'known_context_members_denominator_including_centres':len(known),'opening_date_or_closure_inference':False}
(OUT/'wb_geography_independent_audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2));print(pd.DataFrame(geo).query("radius_km==5 and profile=='raw_code_profile'").to_string(index=False));print(pd.DataFrame(pairs).query("radius_km==5 and date0=='2022-09-29' and date1=='2024-03-11'").to_string(index=False))
