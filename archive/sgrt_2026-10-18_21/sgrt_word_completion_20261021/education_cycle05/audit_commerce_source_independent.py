#!/usr/bin/env python3
"""Independentraw-source/countreadback of anotherauthor's commerce repair."""
from pathlib import Path
import hashlib,json,datetime,re
import numpy as np,pandas as pd,osmium
from shapely import wkb
from shapely.geometry import Point
from scipy.spatial import cKDTree
HERE=Path(__file__).resolve().parent;BASE=HERE.parent;REPO=BASE.parents[1];TARGET=BASE/'commerce_cycle05';OUT=BASE/'reviews/cycle05/commerce_relation_repair_independent_audit.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def chosen(t):return bool(t.get('shop'))or t.get('amenity')in{'bank','atm','post_office','townhall','marketplace'}or t.get('office')=='government'
def group(t):
 a=t.get('amenity')
 if a in{'bank','atm'}:return a
 if a=='post_office':return'post_office'
 if t.get('office')=='government'or a=='townhall':return'administration'
 if a=='marketplace':return'market'
 return'large_retail'if t.get('shop')in{'supermarket','mall','department_store'}else'other_retail'
def normal(v):return re.sub(r'[^а-яa-z0-9]+',' ',str(v).lower().replace('ё','е')).strip()
def xyz(lat,lon):
 a,b=np.radians(lat),np.radians(lon);return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
def km(v):return 12742.0176*np.arcsin(np.clip(v/2,0,1))
class Raw(osmium.SimpleHandler):
 def __init__(self):super().__init__();self.rows={};self.polys={};self.factory=osmium.geom.WKBFactory()
 def relation(self,r):
  t=dict(r.tags)
  if chosen(t):self.rows[r.id]={'tags':t,'members':[{'type':m.type,'ref':m.ref,'role':m.role}for m in r.members],'version':r.version,'timestamp':str(r.timestamp)}
 def area(self,a):
  if a.from_way()or not chosen(dict(a.tags)):return
  try:
   p=wkb.loads(self.factory.create_multipolygon(a),hex=True)
   if p.is_valid and not p.is_empty:self.polys[a.orig_id()]=p
  except Exception:pass

def main():
 receipt=json.loads((TARGET/'relation_recovery_receipt.json').read_text());checks=[]
 def ck(n,truth,detail=None):checks.append({'check':n,'pass':bool(truth),'detail':detail})
 for path,m in receipt['output_files'].items():ck('output_sha:'+path,sha(TARGET/path)==m['sha256']and(TARGET/path).stat().st_size==m['bytes'])
 for name,h in receipt['input_sha256'].items():ck('input_sha:'+name,sha(Path(name)if Path(name).is_absolute()else REPO/name)==h)
 ck('code_sha',sha(TARGET/'recover_commerce_relations.py')==receipt['code_sha256'])
 pbf=Path('/workspace/scratch/sgrt_validation/services2021_reference_complete.osm.pbf');h=Raw();h.apply_file(str(pbf),locations=True,idx='sparse_mem_array')
 raw=pd.read_parquet(TARGET/'relation_source_ledger.parquet');d=pd.read_parquet(TARGET/'service_relations_2021.parquet');u=pd.read_parquet(TARGET/'relation_unresolved_geometry.parquet');old=pd.read_parquet(BASE/'calibration/services_2021_objects.parquet');allobj=pd.read_parquet(TARGET/'services_2021_objects_repaired.parquet');f=pd.read_parquet(TARGET/'services_2021_settlement_features.parquet');axis=pd.read_parquet(BASE/'axis/full_settlement_axis.parquet')
 ck('raw_relation_count_ids',len(h.rows)==1774 and set(h.rows)==set(raw.osm_id));ck('valid_polygon_count_ids',len(h.polys)==1761 and set(h.polys)==set(d.osm_id));ck('unresolved_ids_exactly_remainder',len(u)==13 and set(u.osm_id)==set(h.rows)-set(h.polys))
 ck('allraw_relation_tags_members_version_time',all(json.loads(r.tags_json)==h.rows[r.osm_id]['tags']and json.loads(r.member_refs_json)==h.rows[r.osm_id]['members']and r.source_version==h.rows[r.osm_id]['version']and r.source_last_edit==h.rows[r.osm_id]['timestamp']for _,r in raw.iterrows()))
 ck('all_assembled_wkb_interior_point_exact',all(bytes(r.polygon_wkb)==h.polys[r.osm_id].wkb and h.polys[r.osm_id].covers(Point(r.lon,r.lat))and h.polys[r.osm_id].representative_point().x==r.lon and h.polys[r.osm_id].representative_point().y==r.lat for _,r in d.iterrows()))
 ck('source_dates_before_snapshot',max(pd.Timestamp(v['timestamp'])for v in h.rows.values())<=pd.Timestamp('2021-01-01T21:42:03Z'))
 original=allobj[allobj.osm_type.ne('relation')].reset_index(drop=True);ok=True
 try:pd.testing.assert_frame_equal(original[old.columns],old.reset_index(drop=True),check_dtype=True)
 except AssertionError as e:ok=False;detail=str(e)[:300]
 ck('all_original456966_rows31fields_unchanged',ok and len(original)==456966 and len(old.columns)==31)
 ck('all_raw_assertions_unique_retained',len(allobj)==458727 and allobj.site_id.is_unique and set(old.site_id).issubset(set(allobj.site_id))and set(d.site_id).issubset(set(allobj.site_id)))
 parsed=[json.loads(t)for t in allobj.tags_json];ck('independent_all_raw_service_group_classification',all(group(t)==g for t,g in zip(parsed,allobj.service_group)))
 negative=np.array([group(t)=='other_retail'and t.get('shop')in{'no','vacant','closed','disused','abandoned','demolished'}for t in parsed]);ck('negative_shop_tags_all_retained_uncounted',negative.sum()==501 and not allobj.loc[negative,'count_eligible'].any());ck('old496_new5_negative_counts',(negative[:len(old)].sum(),negative[len(old):].sum())==(496,5))
 # Independentnewrelation address and nearestneighbor replay, separate frommodel.
 ref=axis[axis.lat.notna()&axis.lon.notna()&axis.population_2021.notna()&axis.is_additive_source_unit.eq(True)].reset_index(drop=True);coords=xyz(ref.lat.to_numpy(),ref.lon.to_numpy());tree=cKDTree(coords);pp=xyz(d.lat.to_numpy(),d.lon.to_numpy());dd,ii=tree.query(pp,k=2,workers=1);dd=12742.0176*np.arcsin(np.clip(dd/2,0,1));identity_bad=[]
 names=ref.name.map(normal).to_numpy()
 for j,(_,r)in enumerate(d.iterrows()):
  t=json.loads(r.tags_json);local=next((t[k]for k in ['addr:city','addr:village','addr:hamlet','addr:place','is_in:city']if t.get(k)),None);literal=re.sub(r'^(город|село|деревня|поселок|г|с|д|п)\s+','',normal(local))if local else'';exact=None
  if literal:
   near=tree.query_ball_point(pp[j],2*np.sin(5/12742.0176));same=[k for k in near if names[k]==literal]
   if len(same)==1:exact=ref.iloc[same[0]].id
  candidate=None;d0,d1=dd[j];closest=ref.iloc[ii[j,0]]
  if exact is None and d0<=2.5 and d1>=max(d0*1.5,d0+.25)and(not literal or names[ii[j,0]]==literal)and literal not in {'москва','санкт петербург','санктпетербург','севастополь'}:candidate=closest.id
  if exact!=(r.baseline_uid if pd.notna(r.baseline_uid)else None)or candidate!=(r.candidate_uid if pd.notna(r.candidate_uid)else None):identity_bad.append(r.site_id)
 ck('independent1761_address_and_candidate_replay',not identity_bad,identity_bad[:5])
 # Independentcount reconstruction, explicitidentity takingprecedence.
 strict=set(zip(allobj.loc[allobj.count_eligible&allobj.baseline_uid.notna(),'baseline_uid'],allobj.loc[allobj.count_eligible&allobj.baseline_uid.notna(),'canonical_site_id']))
 ck('strict_mode_boolean',np.array_equal(allobj.count_baseline_eligible,allobj.count_eligible&allobj.baseline_uid.notna()))
 expected_candidate=np.array([bool(ok)and pd.notna(uid)and(uid,c)not in strict for ok,uid,c in zip(allobj.count_eligible,allobj.candidate_uid,allobj.canonical_site_id)])
 ck('candidateadditional_mode_boolean',np.array_equal(allobj.count_candidate_additional_eligible,expected_candidate))
 ck('axis_complete_and_exact_order',len(f)==173527 and f.id.is_unique and f.id.tolist()==axis.id.tolist())
 for g in sorted(allobj.service_group.unique()):
  for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
   z=allobj[allobj.service_group.eq(g)&allobj[f'count_{mode}_eligible']];pairs=z[[key,'canonical_site_id']].drop_duplicates();expected=pairs.groupby(key).size();actual=f.set_index('id')[f'services_osm2021_{g}_{mode}_count'];ck('allNP_counts:'+g+':'+mode,np.array_equal(actual.to_numpy(),actual.index.map(expected).fillna(0).astype(int).to_numpy()))
  total=f[f'services_osm2021_{g}_baseline_count']+f[f'services_osm2021_{g}_candidate_additional_count'];presence=f[f'services_osm2021_{g}_observed_presence'];ck('positive_or_unknown_presence:'+g,presence[total.eq(0)].isna().all()and presence[total.gt(0)].eq(True).all())
 # Rawdedup evidence ratherthantruststatus strings.
 lookup=allobj.set_index('site_id');bad=[]
 for _,r in d[d.recovery_status.eq('same_named_existing_service_site_duplicate')].iterrows():
  ev=json.loads(r.duplicate_evidence_json)
  if not ev:bad.append(r.site_id);continue
  for v in ev:
   q=lookup.loc[v['site_id']];same=normal(r['name'])==normal(q['name'])and bool(normal(r['name']));p=h.polys[r.osm_id];a=xyz([r.lat],[r.lon])[0];b=xyz([q.lat],[q.lon])[0];distance=12742.0176*np.arcsin(np.clip(np.linalg.norm(a-b)/2,0,1));members={(v['type'],v['ref'])for v in json.loads(r.member_refs_json)};member=(q.osm_type[0],int(q.osm_id))in members
   if not(same and q.service_group==r.service_group and(p.covers(Point(q.lon,q.lat))or distance<=.05 or member)):bad.append(r.site_id)
 ck('all34_same_named_aliases_actual_geometry_name_evidence',len(d[d.recovery_status.eq('same_named_existing_service_site_duplicate')])==34 and not bad,bad[:5])
 ck('ambiguous_overlap_statuses_not_counted',not d.loc[d.recovery_status.str.contains('ambiguous|overlap_not_counted'),'count_eligible'].any())
 all_source_ids=set(allobj.site_id)
 ck('canonical_aliases_existing_and_samegroup',all(c in all_source_ids for c in d.canonical_site_id)and all(allobj.groupby('canonical_site_id').service_group.nunique().le(1)))
 ck('no_accepted_new_strict_campus_conflicting_localities',allobj[allobj.count_baseline_eligible].groupby('canonical_site_id').baseline_uid.nunique().le(1).all())
 oldf=pd.read_parquet(BASE/'calibration/services_2021_settlement_features.parquet');counts=[c for c in oldf if c.endswith('_count')];change=f[counts].ne(oldf[counts]).any(axis=1);ck('reported497_changed_NP',int(change.sum())==497)
 ck('input_hashes_still_unchanged',all(sha(Path(n)if Path(n).is_absolute()else REPO/n)==v for n,v in receipt['input_sha256'].items()))
 result={'status':'INDEPENDENT_RAW_COMMERCE_RELATION_AND_NEGATIVE_TAG_REPAIR_AUDIT','reviewer':'education_functions_cycle05 differentdataauthor','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'n_checks':len(checks),'n_failed':sum(not c['pass']for c in checks),'checks':checks,'reviewed_receipt_sha256':sha(TARGET/'relation_recovery_receipt.json'),'source_sha256':receipt['input_sha256'],'reviewed_output_sha256':{str(TARGET/n):m['sha256']for n,m in receipt['output_files'].items()},'code_sha256':sha(Path(__file__)),'scientific_scope':'Correctnessofdatedsourceingestionandreportedcounts; notcompletecommercecensus oractualattractionvalidation'};OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'n_checks':result['n_checks'],'n_failed':result['n_failed'],'failures':[c for c in checks if not c['pass']]},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
