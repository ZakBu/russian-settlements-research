import sys,json,hashlib,re,math
from pathlib import Path
import pandas as pd
import xlrd
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).resolve().parent
CACHE=Path('/dev/shm/settlements-stage71-20261009')
REGIONS='дагестан,тамбовская,воронежская,краснодарский,волгоградская,северная осетия алания,липецкая,самарская,ульяновская,пензенская,кабардино балкарская,саратовская,чеченская,адыгея,ставропольский,ростовская,калмыкия,мордовия,белгородская,астраханская,марий эл,ингушетия'.split(',')
def whole(r): return bool(r.is_additive_settlement_record) and not re.search(r'\(часть|администраци|сельсовет|сельское поселение',normalize(r.settlement_name))
def main():
 obs=pd.read_parquet(CACHE/'applied_state_observations.parquet'); pts=pd.read_parquet(CACHE/'applied_point_snapshot.parquet'); residual=pd.read_csv('/dev/shm/over500-20261009/residual.csv'); residual=residual[residual.region_norm.isin(REGIONS)]
 pts=pts.set_index('target_source_record_id',drop=False); obs=obs[obs.region_norm.isin(REGIONS)].copy(); by=obs.set_index('source_record_id',drop=False); obs['county']=obs.district_raw.map(county_key);obs['name']=obs.name_norm.map(normalize);obs['type']=obs.type_norm.map(normalize)
 inputs={str(CACHE/f):sha(CACHE/f) for f in ['applied_state_observations.parquet','applied_point_snapshot.parquet','applied_component_snapshot.csv.gz']}; inputs['/dev/shm/over500-20261009/residual.csv']=sha(Path('/dev/shm/over500-20261009/residual.csv'))
 books={};checks=[];context={}; roots={s:r for s,r in obs[['source_record_id','root']].itertuples(index=False,name=None)};members={r:set(g.source_record_id) for r,g in obs.groupby('root')}
 component_counties=obs[obs.census_year.ne(2010)&obs.county.ne('')].groupby('root').county.agg(lambda x:set(x)).to_dict()
 # Infer only from independently accepted, distinct native adjacent locality anchors.
 for r in obs[obs.census_year.eq(2010)&obs.county.eq('')&obs.name.isin(set(residual.name_norm.map(normalize)))].itertuples():
  same=obs[obs.census_year.eq(2010)&obs.source_file.eq(r.source_file)&obs.region_norm.eq(r.region_norm)].copy()
  try: sheet=r.source_record_id.rsplit(':',2)[-2]; num=int(r.source_record_id.rsplit(':',1)[-1])
  except: continue
  same=same[same.source_record_id.str.rsplit(':',n=2).str[-2].eq(sheet)]; same['row']=same.source_record_id.str.rsplit(':',n=1).str[-1].astype(int)
  anchors=[]
  for a in same[(same.row-num).abs().le(20)&same.row.ne(num)].itertuples():
   counties=component_counties.get(a.root,set())
   if len(counties)==1 and whole(a): anchors.append((a.row,a.source_record_id,next(iter(counties)),a.name))
  lower=sorted((a for a in anchors if a[0]<num),reverse=True);upper=sorted(a for a in anchors if a[0]>num)
  if not lower or not upper:continue
  lo,hi=lower[0],upper[0]
  if lo[2]!=hi[2] or lo[3]==hi[3]:continue
  path=Path('/workspace/settlements-raw')/r.source_file
  if not path.is_file():continue
  if path not in books:books[path]=xlrd.open_workbook(path,on_demand=True);inputs[str(path)]=sha(path)
  sh=books[path].sheet_by_name(sheet);valid=True;tmp=[]
  for rownum,sid in [(lo[0],lo[1]),(num,r.source_record_id),(hi[0],hi[1])]:
   cells=sh.row_values(rownum-1);name=normalize(by.loc[sid,'settlement_name']);okay=any(name in normalize(c) for c in cells if isinstance(c,str));valid &= okay
   tmp.append(dict(source_record_id=sid,target_source_record_id=r.source_record_id,source_file=str(path),source_sha256=inputs[str(path)],sheet=sheet,row_1based=rownum,literal=json.dumps(cells,ensure_ascii=False),literal_name_verified=okay,inferred_county=lo[2]))
  if valid:context[r.source_record_id]=(lo,hi);obs.loc[obs.source_record_id.eq(r.source_record_id),'county']=lo[2];checks.extend(tmp)
 print('context',len(context),flush=True)
 edges=[];points=[];holds=[];touched=set(); targetids=set(residual.source_record_id)
 def merge(a,b):
  ra,rb=roots[a],roots[b]
  if ra==rb:return True
  if set(by.loc[list(members[ra]),'census_year']) & set(by.loc[list(members[rb]),'census_year']):return False
  members[ra]|=members.pop(rb)
  for s in members[ra]:roots[s]=ra
  return True
 groups=obs[obs.county.ne('')&obs.apply(whole,axis=1)].groupby(['region_norm','name','type','county'])
 for key,g in groups:
  if not targetids.intersection(g.source_record_id):continue
  if g.census_year.duplicated().any():continue
  records=g.to_dict('records'); available=[r for r in records if r['source_record_id'] in pts.index]
  if not available:continue
  donor=sorted(available,key=lambda r:r['census_year'],reverse=True)[0];dp=pts.loc[donor['source_record_id']];xy=(float(dp.latitude),float(dp.longitude))
  if any(distance_km(xy,(float(pts.loc[r['source_record_id'],'latitude']),float(pts.loc[r['source_record_id'],'longitude'])))>5 for r in available):continue
  if any(set(by.loc[list(members[roots[r['source_record_id']]]),'census_year']) & set(by.loc[list(members[roots[donor['source_record_id']]]),'census_year']) for r in records if roots[r['source_record_id']]!=roots[donor['source_record_id']]):continue
  for r in records:
   sid=r['source_record_id'];ds=donor['source_record_id']
   if roots[sid]!=roots[ds]:
    if not merge(sid,ds):raise ValueError('year conflict')
    edges.append(dict(from_source_record_id=sid,to_source_record_id=ds,relation='same_place',decision_status='checked_rule_accepted',admission_rule='unique_exact_native_name_type_region_county_with_checked_physical_source_brackets',name_norm=key[1],type_norm=key[2],region_norm=key[0],county_key=key[3],from_district_raw=r['district_raw'],to_district_raw=donor['district_raw'],county_inference_explicit=sid in context or ds in context,source_context_witness_file=str(OUT/'physical_source_context_checks.csv'),population_boundary_comparability_asserted=False));touched.add(sid);touched.add(ds)
   if sid not in pts.index and (sid in targetids or sid in touched):
    p=dict(target_source_record_id=sid,latitude=xy[0],longitude=xy[1],coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=ds,coordinate_origin_ledger=str(CACHE/'applied_point_snapshot.parquet'),coordinate_origin_ledger_sha256=inputs[str(CACHE/'applied_point_snapshot.parquet')],coordinate_origin_ledger_locator='target_source_record_id='+ds,admission_rule='own_point_continuity_over_accepted_unique_native_county_identity',point_temporal_interpretation='Accepted own representative reused retrospectively; not a census date measurement',direct_historical_coordinate_measurement=False,native_code_binding_asserted=False,boundary_comparability_asserted=False,point_origin_file=dp.get('point_origin_file',''),point_origin_sha256=dp.get('point_origin_sha256',''),point_origin_locator=dp.get('point_origin_locator',''),point_origin_kind=dp.get('point_origin_kind',''));points.append(p);touched.add(sid)
 # Existing accepted component reuse only for whole scope and exact own native name/type.
 added={p['target_source_record_id'] for p in points}
 for r in residual.itertuples():
  sid=r.source_record_id
  if sid in pts.index or sid in added or not whole(r):continue
  comps=obs[obs.source_record_id.isin(members[roots[sid]])];same=comps[comps.name_norm.map(normalize).eq(normalize(r.name_norm))&comps.type_norm.map(normalize).eq(normalize(r.type_norm))&comps.source_record_id.isin(pts.index)]
  if len(same)==0:continue
  d=same.sort_values('census_year').iloc[-1];dp=pts.loc[d.source_record_id];xy=(float(dp.latitude),float(dp.longitude))
  if any(distance_km(xy,(float(pts.loc[s,'latitude']),float(pts.loc[s,'longitude'])))>5 for s in comps.source_record_id if s in pts.index):continue
  points.append(dict(target_source_record_id=sid,latitude=xy[0],longitude=xy[1],coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=d.source_record_id,coordinate_origin_ledger=str(CACHE/'applied_point_snapshot.parquet'),coordinate_origin_ledger_sha256=inputs[str(CACHE/'applied_point_snapshot.parquet')],coordinate_origin_ledger_locator='target_source_record_id='+d.source_record_id,admission_rule='own_point_reuse_in_existing_accepted_whole_native_component',point_temporal_interpretation='Accepted own representative reused retrospectively; not a census date measurement',direct_historical_coordinate_measurement=False,boundary_comparability_asserted=False));added.add(sid);touched.add(sid)
 dispositions=[]
 for r in residual.itertuples():
  sid=r.source_record_id;changed=sid in touched
  reason='accepted_stable_native_county_identity_or_existing_component_ownpoint' if changed else ('typed_literal_part_no_whole_NP_ownpoint_projection' if not whole(r) else 'unresolved_source_identity_or_ownpoint_requires_further_source')
  dispositions.append(dict(source_record_id=sid,name=r.settlement_name,year=r.census_year,region=r.region_norm,decision='accepted_delta' if changed else 'held',reason=reason,has_ownpoint_after=sid in pts.index or sid in added or sid in {p['target_source_record_id'] for p in points},component_years_after=','.join(map(str,sorted(set(by.loc[list(members[roots[sid]]),'census_year']))))))
 pd.DataFrame(edges,columns=['from_source_record_id','to_source_record_id','relation','decision_status','admission_rule','name_norm','type_norm','region_norm','county_key','from_district_raw','to_district_raw','county_inference_explicit','source_context_witness_file','population_boundary_comparability_asserted']).to_csv(OUT/'accepted_identity_edge_delta.csv',index=False)
 pd.DataFrame(points,columns=sorted(set(k for p in points for k in p))).to_csv(OUT/'accepted_point_use_delta.csv',index=False)
 pd.DataFrame(checks).to_csv(OUT/'physical_source_context_checks.csv',index=False);pd.DataFrame(dispositions).to_csv(OUT/'dispositions.csv',index=False)
 receipt=dict(stage=71,regions=REGIONS,residual_rows=len(residual),accepted_identity_edges=len(edges),accepted_point_uses=len(points),changed_residual_rows=len(touched&targetids),source_population_values_modified=False,boundary_comparability_asserted=False,inputs_sha256=inputs,outputs_sha256={p.name:sha(p) for p in OUT.glob('*.csv')})
 (OUT/'manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['inputs_sha256','outputs_sha256']},ensure_ascii=False))
if __name__=='__main__':main()
