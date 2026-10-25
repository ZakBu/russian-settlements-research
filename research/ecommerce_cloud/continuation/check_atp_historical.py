"""Independent audits of ATP derived tables and sampled spherical geography.

No production matcher is imported. Text normalization follows the declared
matching rule; independent brute-force Haversine checks the geometric search.
PASS does not validate catalogue completeness, dates of openings, legal
boundaries, trips, functions, or causal effects.
"""
from pathlib import Path
from collections import defaultdict
import hashlib
import json
import math
import re
import sys
import unicodedata
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "work/sources/research/ecommerce_settlement_20261024"
OUT = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "work/ecommerce_atp_analysis")
RAW = ROOT / (sys.argv[2] if len(sys.argv) > 2 else "work/ecommerce_atp_history")
KEY = "source_record_id_2021"
PINS = {
 "2023-10-28-13-32-45": ("0838baa3e8ee3b6caa161c9034f08c1dab9943eeb2664d126384fcda200dbbe0",29250,26281),
 "2023-12-30-13-32-01": ("16e903e7d3f52ae2fb764737d129a244429bc09561bd61719c6ded694b472b45",34069,30425),
 "2024-03-30-13-32-35": ("7563859c886ca878225524f1f4642248ed1390f26fc0dc9ce4540c3294388a8b",38455,34192),
 "2024-06-29-13-32-11": ("8d5e5ba3ea6c0c6666d02611e20e8611905d1a2997dd69c854b34df6c75a86f2",42805,37867),
 "2024-09-07-13-32-11": ("b0bd9fdf68da6995d3947f8d0540bf43bd5e22be3fa52e806e4eeabbac485729",47472,42104),
 "2024-12-28-13-31-57": ("106c7739077c78c50dbd5e6bf0413b8f27a71d7f6f054da7b50c09f314b1a25e",61595,55726),
}
def yes(v):
 return str(v).strip().lower() in {"true","1"}
def eq(a,b):
 assert math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-7),(a,b)
def csv(name):
 return pd.read_csv(OUT/name,keep_default_na=False)
def sha(p):
 return hashlib.sha256(p.read_bytes()).hexdigest()
def nullable(v):
 return None if pd.isna(v) or v=="" else str(v)

summary=json.loads((OUT/"atp_wb_analysis_summary.json").read_text())
links=pd.read_parquet(OUT/"atp_wb_symmetric_links.parquet")
assert set(links.run_id)==set(PINS) and not links.run_id.str.contains("2026").any()
assert not links.duplicated(["run_id","country_scope","country_reported","source_ref"]).any()
all_links=links[links.country_scope=="all_countries"]
source_rows_checked=0
for run,(digest,n,nru) in PINS.items():
 p=RAW/(run+"_wildberries.geojson")
 assert sha(p)==digest
 features=json.loads(p.read_bytes())["features"]
 assert len(features)==n
 raw={}
 for f in features:
  props=f["properties"]
  cc=str(props.get("addr:country") or props.get("country") or "").upper()
  ref=str(props.get("ref") or "")
  assert (cc,ref) not in raw
  raw[cc,ref]=f
 assert sum(cc=="RU" for cc,ref in raw)==nru
 g=all_links[all_links.run_id==run]
 assert len(g)==n
 assert set(zip(g.country_reported,g.source_ref))==set(raw)
 for r in g.itertuples(index=False):
  f=raw[r.country_reported,r.source_ref]
  assert f["geometry"]["type"]=="Point"
  eq(r.longitude,f["geometry"]["coordinates"][0])
  eq(r.latitude,f["geometry"]["coordinates"][1])
  props=f["properties"]
  address=str(props.get("addr:full") or props.get("addr_full") or props.get("address") or "")
  assert r.address==address
  source_rows_checked+=1
 ru=links[(links.run_id==run)&(links.country_scope=="RU_only")]
 assert len(ru)==nru
 a=g[g.country_reported=="RU"].set_index(["country_reported","source_ref"]).sort_index()
 b=ru.set_index(["country_reported","source_ref"]).sort_index()
 for col in [KEY+"_"+str(k)+"km" for k in (1,5,10)]:
  assert a[col].fillna("").tolist()==b[col].fillna("").tolist()

axis=pd.read_parquet(BASE/"national/national_target_source2021.parquet")
context=pd.read_parquet(BASE/"history_stage_20261024/centres/settlement_admin_context_main2021.parquet")
system=pd.read_csv(BASE/"settlement_role_stage_20261024/system/centre_system_demography.csv")
assert len(axis)==144151 and axis[KEY].is_unique and context[KEY].is_unique
medium=set(system.loc[system.medium_primary2002.map(yes),KEY])
assert len(medium)==1273
inhabited=set(axis.loc[axis.population_2021>0,KEY])
groups={}
for vintage in ("20200110","20211103"):
 col="administrative_centre_source_record_id_2021_"+vintage
 known=context["context_status_"+vintage]=="accepted_administrative_parent_and_centre"
 groups[vintage]={cid:set(g[KEY]) for cid,g in context[known].groupby(col)}

inventory=csv("atp_wb_linkage_inventory.csv").set_index(["run_id","country_scope","radius_km"])
cases=csv("atp_wb_1273_contexts.csv")
casekeys=["run_id","country_scope","radius_km","context_vintage",KEY]
cases.context_vintage=cases.context_vintage.astype(str)
assert not cases.duplicated(casekeys).any()
case_lookup=cases.set_index(casekeys)
counts={}
context_checks=0
for (run,scope),g in links.groupby(["run_id","country_scope"]):
 for radius in (1,5,10):
  col=KEY+"_"+str(radius)+"km"
  accepted=g[g[col].notna()]
  count=accepted[col].value_counts().to_dict()
  positive=set(count)
  counts[run,scope,radius]=count
  z=inventory.loc[run,scope,radius]
  assert len(g)==int(z.objects_in_country_scope)
  assert len(accepted)==int(z.linked_objects)
  assert len(positive)==int(z.positive_nodes)
  for vintage in ("20200110","20211103"):
   for cid in medium:
    row=case_lookup.loc[run,scope,radius,vintage,cid]
    members=groups[vintage].get(cid)
    others=(members-{cid}) if members is not None else set()
    living=others&inhabited
    observed=living&positive
    assert yes(row.context_has_accepted_members)==(members is not None)
    assert int(row.other_accepted_members)==len(others)
    assert int(row.other_inhabited_members2021)==len(living)
    assert int(row.positive_other_inhabited_members)==len(observed)
    assert int(row.positive_other_objects)==sum(count[x] for x in observed)
    assert yes(row.centre_positive_record)==(cid in positive)
    assert int(row.centre_observed_objects)==count.get(cid,0)
    context_checks+=1

pair=csv("atp_wb_1273_paired_contexts.csv")
pair.context_vintage=pair.context_vintage.astype(str)
pairkeys=["first_run","last_run","country_scope","radius_km","context_vintage",KEY]
assert not pair.duplicated(pairkeys).any()
for row in pair.itertuples(index=False):
 cid=getattr(row,KEY)
 a=case_lookup.loc[row.first_run,row.country_scope,row.radius_km,row.context_vintage,cid]
 b=case_lookup.loc[row.last_run,row.country_scope,row.radius_km,row.context_vintage,cid]
 assert yes(row.centre_positive_first)==yes(a.centre_positive_record)
 assert yes(row.centre_positive_last)==yes(b.centre_positive_record)
 assert int(row.positive_periphery_first)==int(a.positive_other_inhabited_members)
 assert int(row.positive_periphery_last)==int(b.positive_other_inhabited_members)
 assert int(row.observed_positive_periphery_difference)==int(row.positive_periphery_last)-int(row.positive_periphery_first)

ps=csv("atp_wb_1273_paired_summary.csv")
ps.context_vintage=ps.context_vintage.astype(str)
for s in ps.itertuples(index=False):
 g=pair[(pair.first_run==s.first_run)&(pair.last_run==s.last_run)&
        (pair.country_scope==s.country_scope)&(pair.radius_km==s.radius_km)&
        (pair.context_vintage==s.context_vintage)]
 assert len(g)==1273
 both=g.centre_positive_first.map(yes)&g.centre_positive_last.map(yes)
 supported=g.other_inhabited_members2021.astype(int)>0
 change=g.observed_positive_periphery_difference.astype(int)
 check={
  "all_medium_centres_n":len(g),
  "accepted_inhabited_periphery_contexts_n":int(supported.sum()),
  "centres_positive_in_both_n":int(both.sum()),
  "periphery_positive_count_increased_all_n":int((supported&(change>0)).sum()),
  "periphery_positive_count_decreased_all_n":int((supported&(change<0)).sum()),
  "positive_both_centres_with_periphery_increase_n":int((both&supported&(change>0)).sum()),
  "positive_both_centres_with_periphery_decrease_n":int((both&supported&(change<0)).sum()),
 }
 for field,val in check.items():
  assert val==int(getattr(s,field)),(field,val,getattr(s,field))

# All-axis Haversine search, independent of KDTree and production helpers.
points=axis[axis.accepted_point_present_2021.map(yes)].reset_index(drop=True)
assert len(points)==144149
lat=np.radians(points.accepted_latitude_2021.to_numpy())
lon=np.radians(points.accepted_longitude_2021.to_numpy())
def normalize(s):
 s=unicodedata.normalize("NFKC",str(s)).lower().replace("ё","е")
 return re.sub(r"\s+"," ",re.sub(r"[^\w\s-]"," ",s)).strip()
prefix=re.compile(r"^(?:город|г\.?|село|с\.?|деревня|д\.?|хутор|х\.?|станица|ст-ца|поселок городского типа|рабочий поселок|пгт\.?|р\.?\s*п\.?|поселок|пос\.?|п\.?|аул|слобода|сл\.?|станция|ст\.?)\s+",re.I)
def tokens(address):
 result=set()
 for x in str(address).lower().replace("ё","е").split(",")[:4]:
  x=re.sub(r"\([^)]*\)"," ",x).strip()
  x=normalize(prefix.sub("",x).strip())
  if x:result.add(x)
 return result
names=points.name_2021.map(normalize).to_numpy()
ids=points[KEY].to_numpy()
geo_checks=0
wgs=[]
try:
 from geographiclib.geodesic import Geodesic
except ImportError:
 Geodesic=None
for run,g in all_links.groupby("run_id",sort=True):
 g=g.sort_values(["country_reported","source_ref"]).reset_index(drop=True)
 chosen=np.linspace(0,len(g)-1,min(40,len(g)),dtype=int)
 for index in chosen:
  row=g.iloc[int(index)]
  la,lo=math.radians(row.latitude),math.radians(row.longitude)
  h=np.sin((lat-la)/2)**2+np.cos(la)*np.cos(lat)*np.sin((lon-lo)/2)**2
  distance=2*6371.0088*np.arcsin(np.sqrt(np.clip(h,0,1)))
  named=np.isin(names,list(tokens(row.address)))
  for radius in (1,5,10):
   found=np.flatnonzero(named&(distance<=radius))
   expected=ids[found[0]] if len(found)==1 else None
   saved=nullable(row[KEY+"_"+str(radius)+"km"])
   assert saved==expected,(run,int(index),radius,saved,expected)
   if expected is not None:
    eq(distance[found[0]],row["distance_km_"+str(radius)+"km"])
   geo_checks+=1
  found=np.flatnonzero(named&(distance<=10))
  if Geodesic is not None and len(found)==1:
   p=points.iloc[int(found[0])]
   ellipsoid=Geodesic.WGS84.Inverse(row.latitude,row.longitude,p.accepted_latitude_2021,p.accepted_longitude_2021)["s12"]/1000
   sphere=float(distance[found[0]])
   wgs.append({"sphere_km":sphere,"WGS84_km":ellipsoid,
               "crosses_any_radius":any((sphere<=r)!=(ellipsoid<=r) for r in (1,5,10))})

coexistence=summary.get("demographic_coexistence",{})
demojoin_checks=0
if coexistence.get("status")=="descriptive_coexistence_joined":
 demo_path=ROOT/coexistence["source_path"]
 assert sha(demo_path)==coexistence["source_sha256"]
 demo=pd.read_csv(demo_path,keep_default_na=False)
 demo=demo[demo.medium_primary2002.map(yes)&demo.positive_other_population_all_years.map(yes)].set_index(KEY)
 paths=list(OUT.glob("atp_wb_demography*_descriptive_join.csv"))
 assert len(paths)==1
 joined=pd.read_csv(paths[0],keep_default_na=False)
 assert joined[KEY].is_unique and set(joined[KEY])==set(demo.index)
 assert len(joined)==coexistence["n"]
 for r in joined.itertuples(index=False):
  cid=getattr(r,KEY)
  for field in ("own_change2023_2025_pct","other_change2023_2025_pct","centre_share_change2023_2025_pp"):
   eq(getattr(r,field),demo.loc[cid,field])
  expected=pair[(pair[KEY]==cid)&(pair.first_run=="2023-10-28-13-32-45")&
                (pair.last_run=="2024-09-07-13-32-11")&(pair.radius_km==5)&
                (pair.context_vintage=="20200110")&(pair.country_scope=="all_countries")]
  assert len(expected)==1
  eq(r.observed_positive_periphery_difference,expected.iloc[0].observed_positive_periphery_difference)
  assert yes(r.observed_periphery_positive_count_increased)==(r.observed_positive_periphery_difference>0)
  demojoin_checks+=1
 for s in coexistence["groups"]:
  g=joined[joined.observed_periphery_positive_count_increased.map(yes)==s["observed_periphery_positive_count_increased"]]
  assert len(g)==s["centres_n"]
  assert int((g.centre_share_change2023_2025_pp>0).sum())==s["demographic_share_increased_n"]
  assert int((g.own_change2023_2025_pct<0).sum())==s["own_population_declined_n"]
  eq(g.centre_share_change2023_2025_pp.median(),s["median_demographic_share_change_pp"])
  eq(g.own_change2023_2025_pct.median(),s["median_own_population_change_pct"])
  eq(g.other_change2023_2025_pct.median(),s["median_other_population_change_pct"])

result={
 "status":"PASS","raw_bodies_hash_verified":len(PINS),
 "raw_source_rows_checked":source_rows_checked,
 "context_rows_independently_reconstructed":context_checks,
 "paired_context_rows_checked":len(pair),
 "paired_summary_rows_checked":len(ps),
 "sampled_object_radius_Haversine_checks":geo_checks,
 "demographic_join_rows_checked":demojoin_checks,
 "geographiclib_available":Geodesic is not None,
 "WGS84_sample_comparisons":len(wgs),
 "WGS84_sample_threshold_crossings":sum(x["crosses_any_radius"] for x in wgs),
 "WGS84_max_absolute_difference_km":max((abs(x["sphere_km"]-x["WGS84_km"]) for x in wgs),default=None),
 "geographic_metric_note":"WGS84 vs sphere is sensitivity, not an exact-equality assertion.",
 "limits":["Arithmetic and sampled declared-rule geometry only.",
           "No independent address-type or legal-boundary ground truth.",
           "No catalogue completeness, opening/closure or functional validation.",
           "No causal effect is validated."]
}
(OUT/"independent_atp_check.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("INDEPENDENT_ATP_CHECK_BEGIN")
print(json.dumps(result,ensure_ascii=False,indent=2))
print("INDEPENDENT_ATP_CHECK_END")
