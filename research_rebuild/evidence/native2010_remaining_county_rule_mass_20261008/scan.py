import sys,json,collections,re,importlib.util
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
sp=importlib.util.spec_from_file_location('fm',R/'research_rebuild/evidence/working_full_chain_20261007/replay_additional_native_20261008.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm)
ALIASES={'киров и кировский':'кировский','павловский посад':'павлово посадский','ступино':'ступинский','чехов':'чеховский','луховицы':'луховицкий','алексин':'алексинский'}
TYPES={'рп':'пгт','поселок городского типа':'пгт','рабочий поселок':'пгт','поселок':'посёлок'}
def cn(v):
 k=county_key(v);return ALIASES.get(k,k)
def nm(v):
 n=normalize(v);n=re.sub(r'^(?:поселок|посёлок|село|деревня|станица|аул|пгт|рп|п\.|с\.|д\.)\s+','',n)
 n=re.sub(r'\s+(?:п\.|пгт|рп)$','',n)
 return re.sub(r'["«»]','',n)
def ty(v):return TYPES.get(normalize(v),normalize(v))
def finite_module():return fm

def discover(s):
 members=collections.defaultdict(list)
 for sid,y in s.obs[['source_record_id','census_year']].itertuples(index=False,name=None):members[s.uf.find(sid)].append(sid)
 idx=collections.defaultdict(list)
 for row in s.obs.itertuples():idx[(int(row.census_year),row.region_norm,nm(row.settlement_name))].append(row.source_record_id)
 ctxpath=R/'research_rebuild/evidence/secondary_2010_county_context_application_20261007/all_selected_competitor_county_context.csv.gz';ctx=pd.read_csv(ctxpath,keep_default_na=False).set_index('source_record_id').to_dict('index')
 exclusions=set();expins={}
 for rel in ['working_full_chain_20261007/qualified_scope_source_id_credit_union.csv','working_full_chain_20261007/named_merger_lineage_constituents.csv','working_full_chain_20261007/complete_territorial_scope_constituents.csv','working_full_chain_20261007/direct_inclusion_transformation_path_native_credit_union.csv','uncached_missing2010_dated_source_mass_20261008/accepted_qualified_native_source_ID_credit_union.csv','absorbed_residual_direct_events_next_20261008/candidate_direct_event_native_credit_union.csv.gz']:
  p=R/'research_rebuild/evidence'/rel
  if p.exists():
   f=pd.read_csv(p,keep_default_na=False); snapshot=O/('baseline49_exclusion_'+str(len(expins))+'.csv.gz');f.to_csv(snapshot,index=False,compression={'method':'gzip','mtime':0});expins[str(snapshot)]=sha(snapshot)
   for col in f:
    if 'source_record_id' in col and not col.endswith('json'):exclusions.update(f[col].astype(str))
 def county(sid):
  row=s.by_id.loc[sid];return cn(row.district_raw) or cn(ctx.get(sid,{}).get('inferred_county_key',''))
 def anchors(row):
  sid=row.source_record_id
  if not sid.startswith('2010:'):return []
  prefix=sid.rsplit(':',1)[0]+':';rn=int(sid.rsplit(':',1)[1]);out=[]
  for sign in [-1,1]:
   n=0
   for dr in range(1,25):
    aid=prefix+str(rn+sign*dr)
    if aid not in s.by_id.index:continue
    ar=s.by_id.loc[aid]
    if ar.region_norm!=row.region_norm:break
    current=[i for i in members[s.uf.find(aid)] if int(s.by_id.loc[i,'census_year'])==2021]
    if len(current)==1 and s.years[s.uf.find(aid)]=={2002,2010,2021}:
     n+=1;oldids=[i for i in members[s.uf.find(aid)] if int(s.by_id.loc[i,'census_year'])==2002]
     out.append({'offset':sign*dr,'anchor_native2002_source_record_id':oldids[0],'native_source_record_id':aid,'name':ar.settlement_name,'native_current_source_record_id':current[0],'current_county_raw':s.by_id.loc[current[0],'district_raw'],'county_key':county(current[0])})
     if n>=3:break
  return out
 rows=[];candidates=[];rivals=[];contexts=[]
 selected=s.obs[s.obs.census_year.eq(2010)&s.obs.population.ge(500)&s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь'])].sort_values('population',ascending=False)
 for b in selected.itertuples():
  root=s.uf.find(b.source_record_id);ys=s.years[root]
  if ys=={2002,2010,2021} or b.source_record_id in exclusions:continue
  aa=anchors(b);dc=county(b.source_record_id)
  inherited_current=[i for i in members[root] if int(s.by_id.loc[i,'census_year'])==2021]
  if len(inherited_current)==1:dc=county(inherited_current[0]) or dc
  if not dc:
   left=[x for x in aa if x['offset']<0];right=[x for x in aa if x['offset']>0]
   if left and right and left[0]['county_key']==right[0]['county_key']:dc=left[0]['county_key']
  olds=idx.get((2002,b.region_norm,nm(b.settlement_name)),[]);allcurrents=idx.get((2021,b.region_norm,nm(b.settlement_name)),[]);currents=[i for i in members[root] if int(s.by_id.loc[i,'census_year'])==2021] or idx.get((2021,b.region_norm,nm(b.settlement_name)),[])
  for sid in olds+allcurrents:
   z=s.by_id.loc[sid];rivals.append({'target2010_source_record_id':b.source_record_id,'candidate_source_record_id':sid,'year':z.census_year,'name':z.settlement_name,'type':z.settlement_type,'county_raw':z.district_raw,'county_key':county(sid),'population':z.population,'component_years':str(sorted(s.years[s.uf.find(sid)])),'point_present':sid in s.point_rows})
  oldtyped=[i for i in olds if ty(s.by_id.loc[i,'settlement_type'])==ty(b.settlement_type)]
  oldcounty=[i for i in oldtyped if dc and county(i)==dc]
  oldbracket=[]
  if len(oldcounty)>1:
   for l in [x for x in aa if x['offset']<0]:
    for r in [x for x in aa if x['offset']>0]:
     if l['county_key']!=dc or r['county_key']!=dc or l['name']==r['name']:continue
     li=l['anchor_native2002_source_record_id'];ri=r['anchor_native2002_source_record_id']
     if li.rsplit(':',1)[0]!=ri.rsplit(':',1)[0] or not li.startswith('2002:'):continue
     try:lo,hi=sorted([int(li.rsplit(':',1)[1]),int(ri.rsplit(':',1)[1])])
     except ValueError:continue
     if hi-lo>120:continue
     chosen=[i for i in oldcounty if i.rsplit(':',1)[0]==li.rsplit(':',1)[0] and lo<int(i.rsplit(':',1)[1])<hi]
     if len(chosen)==1:oldbracket.append((chosen[0],l,r,lo,hi))
   if oldbracket and len({p[0] for p in oldbracket})==1:oldcounty=[oldbracket[0][0]]
  curtyped=currents if inherited_current else [i for i in currents if ty(s.by_id.loc[i,'settlement_type'])==ty(b.settlement_type)]
  curcounty=[i for i in curtyped if dc and county(i)==dc]
  currentbracket=[]
  if len(curcounty)>1:
   for l in [x for x in aa if x['offset']<0]:
    for r in [x for x in aa if x['offset']>0]:
     if l['county_key']!=dc or r['county_key']!=dc or l['name']==r['name']:continue
     li=l['native_current_source_record_id'];ri=r['native_current_source_record_id']
     if li.rsplit(':',1)[0]!=ri.rsplit(':',1)[0]:continue
     lo,hi=sorted([int(li.rsplit(':',1)[1]),int(ri.rsplit(':',1)[1])])
     if hi-lo>120:continue
     chosen=[i for i in curcounty if i.rsplit(':',1)[0]==li.rsplit(':',1)[0] and lo<int(i.rsplit(':',1)[1])<hi]
     if len(chosen)==1:currentbracket.append((chosen[0],l,r,lo,hi))
   if currentbracket and len({p[0] for p in currentbracket})==1:curcounty=[currentbracket[0][0]]
  if len(oldtyped)==1 and not county(oldtyped[0]):oldcounty=oldtyped
  if not dc:
   if len(oldtyped)==1:oldcounty=oldtyped
   if len(curtyped)==1:curcounty=curtyped
  reason=''
  if 2002 in ys:reason='already_native02_missing_current'
  elif not olds:reason='no_literal_native02_name'
  elif len(oldcounty)!=1:reason='old_name_type_county_ambiguous_or_mismatch'
  elif s.years[s.uf.find(oldcounty[0])]&ys:reason='old_component_occupied_year'
  elif len(curcounty)!=1:reason='current_name_type_county_ambiguous_or_mismatch'
  elif curcounty[0] not in s.point_rows:reason='current_no_accepted_ownpoint'
  elif not (oldbracket and (inherited_current or currentbracket)) and dc and len([i for i in idx.get((2010,b.region_norm,nm(b.settlement_name)),[]) if ty(s.by_id.loc[i,'settlement_type'])==ty(b.settlement_type) and county(i)==dc])>1:reason='same_year2010_same_class_county_rivals'
  else:
   old=oldcounty[0];current=curcounty[0];ocr=s.uf.find(old);ccr=s.uf.find(current)
   if ccr!=root and ccr!=ocr and s.years[ccr]&(ys|s.years[ocr]):reason='current_component_occupied_year'
   elif any(i in s.conflicting_point_targets for i in members[root]+members[ocr]+members[ccr]):reason='existing_point_conflict'
   else:
    pp=s.point_rows[current];oldpoints=[s.point_rows[i] for i in members[root]+members[ocr] if i in s.point_rows]
    if any(distance_km((p['latitude'],p['longitude']),(pp['latitude'],pp['longitude']))>5 for p in oldpoints):reason='accepted_historical_point_contradicts_current'
    else:
     candidates.append({'native2010_source_record_id':b.source_record_id,'native2002_source_record_id':old,'native2021_source_record_id':current,'name':b.settlement_name,'region':b.region_norm,'type':b.settlement_type,'county_key':dc,'protected2010_population':b.population,'old_county_raw':s.by_id.loc[old,'district_raw'],'current_county_raw':s.by_id.loc[current,'district_raw'],'county_source_anchors_json':json.dumps(aa,ensure_ascii=False),'old_native_two_sided_source_bracket_json':json.dumps(oldbracket,ensure_ascii=False),'current_native_two_sided_source_bracket_json':json.dumps(currentbracket,ensure_ascii=False),'existing2010_current_identity_allows_printed_class_change':bool(inherited_current),'old_literal_region_name_rivals':len(olds),'current_literal_region_name_rivals':len(allcurrents),'source_positive_point_json':json.dumps(pp,ensure_ascii=False)});reason='positive_literal_native_county_ownpoint_candidate'
  rows.append({'native2010_source_record_id':b.source_record_id,'name':b.settlement_name,'region':b.region_norm,'type':b.settlement_type,'population':b.population,'component_years':str(sorted(ys)),'county_key':dc,'old_name_rivals':len(olds),'old_type_rivals':len(oldtyped),'old_type_county_rivals':len(oldcounty),'current_candidates':len(curcounty),'outcome':reason})
 return rows,candidates,rivals,expins,ctxpath

if __name__=='__main__':
 s=load(49);rows,positive,rivals,expins,ctxpath=discover(s)
 for name,f in [('ranked_remaining2010_mass.csv.gz',rows),('positive_literal_native_county_ownpoint_candidates.csv.gz',positive),('all_native_name_type_county_competitors.csv.gz',rivals)]:pd.DataFrame(f).to_csv(O/name,index=False,compression={'method':'gzip','mtime':0})
 r={'baseline_stage':49,'before':s.metrics(),'before_finite_all3_all_points':fm.finite(s),'remaining_native2010_ge500':len(rows),'gross_native2010_population':sum(x['population'] for x in rows),'positive_candidates':len(positive),'positive_native2010_population':sum(x['protected2010_population'] for x in positive),'outcomes':dict(collections.Counter(x['outcome'] for x in rows)),'exclusion_input_pins':expins,'source_context_pin':{'path':str(ctxpath),'sha256':sha(ctxpath)}};(O/'scan_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False))
