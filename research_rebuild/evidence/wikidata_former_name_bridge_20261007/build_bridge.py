"""Candidate-only own-entity exact former-name bridge; no frozen ledger mutation."""
import sys,json,gzip,re,itertools
from pathlib import Path
from collections import Counter
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
OUT=Path(__file__).resolve().parent
state=load(stage=11);baseline=state.metrics();inputs={str(p):sha(p) for p in state.inputs}
obs=state.obs.copy();obs['n']=obs.settlement_name.map(normalize);obs['d']=obs.district_raw.map(county_key)
obs=obs[obs.is_additive_settlement_record.fillna(False)]
widepath=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');wide=pd.read_parquet(widepath);inputs[str(widepath)]=sha(widepath)
current=wide[wide.source_record_id.isin(obs.source_record_id)].copy();current=current[current.wikidata_name_exact_label & ~current.entity_competition_across_tsv_or_truthy & ~current.source_observation_competition_for_exact_oktmo]
byqid={q:g for q,g in current.groupby('wikidata_qid')}; names=set(obs.n)
witnesses=[];entities={}
def witness(q,label,old,kind,path,locator,raw,dated=False):
 old=normalize(old)
 if old and old in names and old!=normalize(label) and q in byqid:
  witnesses.append(dict(qid=q,current_label=label,former_name=old,witness_kind=kind,witness_file=str(path),witness_locator=locator,witness_raw=raw,dated_rename_witness=dated))
for p in list(Path('/workspace/settlements-raw/data/raw/wikidata_entities_full').glob('batch*.json.gz'))+[OUT/'live_entities.json',ROOT/'evidence/top_large_missing_year_sources_20261007/live_wikidata_entities.json.gz',ROOT/'evidence/full_chain_missing_points_20261007/top30pointuses/wikidata_entities.json']:
 if not p.exists():continue
 d=json.load(gzip.open(p,'rt') if p.suffix=='.gz' else p.open());inputs[str(p)]=sha(p)
 for q,e in d.get('entities',{}).items():
  entities[q]=e;label=e.get('labels',{}).get('ru',{}).get('value','')
  for i,a in enumerate(e.get('aliases',{}).get('ru',[])):witness(q,label,a['value'],'own_entity_alias',p,f'entities.{q}.aliases.ru[{i}]',a['value'])
  for c in e.get('claims',{}).get('P1448',[]):
   v=c['mainsnak'].get('datavalue',{}).get('value',{})
   if isinstance(v,dict) and v.get('language')=='ru':witness(q,label,v.get('text',''),'own_entity_P1448',p,c['id'],json.dumps(c,ensure_ascii=False),bool(c.get('qualifiers')))
articleproof={}
for p in Path('/workspace/settlements-raw/data/raw/wikipedia_articles').glob('batch*.json.gz'):
 d=json.load(gzip.open(p,'rt'));requested={r.get('article_title'):r.get('wikidata_id_effective') for r in d['requested']}
 pages=d.get('payload',{}).get('query',{}).get('pages',[])
 for page in (pages if isinstance(pages,list) else pages.values()):
  title=page.get('title','');q=requested.get(title)
  if q not in byqid:continue
  rev=page.get('revisions',[{}])[0];text=rev.get('slots',{}).get('main',{}).get('content','')
  m=re.search(r'^\s*\|\s*прежние (?:имена|названия)\s*=([^\n]+)',text,re.M)
  if not m:continue
  vals=re.findall(r'\{\{НП-ПН\|([^}]+)',m[1])
  aliases=[]
  for v in vals:aliases += [x.strip() for x in v.split('|') if not re.fullmatch(r'\d{1,4}',x.strip())]
  for a in aliases:
   witness(q,title,a,'own_article_former_names_infobox',p,f'pageid={page["pageid"]};revid={rev.get("revid")};former_names',m[0],True)
  if any(normalize(a) in names for a in aliases):
   articleproof[q]=dict(path=str(p),pageid=page['pageid'],revid=rev.get('revid'),title=title,former_names=m[0],context_lines=[s[:1500] for s in text.splitlines() if ('район' in s or '2020' in s or 'переимен' in s)][:30]);inputs[str(p)]=sha(p)
# Exact own-article spelling witness for printed Центорой, distinct from Центарой P1448.
q='Q1873736'
if q in articleproof:
 a=articleproof[q];p=Path(a['path']);d=json.load(gzip.open(p,'rt'));page=next(v for v in d['payload']['query']['pages'] if v['pageid']==a['pageid']);t=page['revisions'][0]['slots']['main']['content']
 for s in t.splitlines():
  if 'Село Центорой / Чечня' in s:witness(q,'Ахмат-Юрт','Центорой','own_article_exact_secondary_reference_title',p,f'pageid={a["pageid"]};revid={a["revid"]};reference_title',s,False)
W=pd.DataFrame(witnesses).drop_duplicates(['qid','former_name','witness_kind','witness_file']);W.to_csv(OUT/'former_name_witness_inventory.csv',index=False)
(OUT/'own_article_context_witnesses.json.gz').write_bytes(gzip.compress(json.dumps(articleproof,ensure_ascii=False).encode(),mtime=0))
rows=[];holds=[];seen=set();already=0
lookup={(n,r):g for (n,r),g in obs.groupby(['n','region_norm'])}
unique_counts=obs.groupby(['census_year','n','region_norm','d']).size().to_dict()
for w in W.to_dict('records'):
 for c in byqid[w['qid']].to_dict('records'):
  bid=c['source_record_id'];b=state.by_id.loc[bid];ck=county_key(b.district_raw)
  pool=lookup.get((w['former_name'],b.region_norm),obs.iloc[:0]);pool=pool[pool.census_year!=b.census_year]
  for a in pool.itertuples():
   aid=a.source_record_id;pair=(aid,bid)
   if pair in seen:continue
   seen.add(pair)
   if state.uf.find(aid)==state.uf.find(bid):already+=1;continue
   transfer=(w['qid']=='Q4230262' and a.d=='грозненский' and ck=='аргун' and 'До 1 января 2020' in str(articleproof.get(w['qid'],{})))
   reasons=[]
   if a.d!=ck and not transfer:reasons.append('explicit_county_mismatch_without_own_article_transfer')
   if len(pool[(pool.census_year==a.census_year)&(pool.d==a.d)])!=1:reasons.append('former_name_year_county_not_unique')
   if unique_counts.get((b.census_year,normalize(b.settlement_name),b.region_norm,ck),0)!=1:reasons.append('current_name_year_county_not_unique')
   if state.years[state.uf.find(aid)]&state.years[state.uf.find(bid)]:reasons.append('repeated_year_graph_conflict')
   ap=state.point_rows.get(aid);bp=state.point_rows.get(bid);dist=None
   if bp and pd.notna(a.latitude) and pd.notna(a.longitude) and (a.latitude,a.longitude)!=(0,0) and distance_km((a.latitude,a.longitude),(bp['latitude'],bp['longitude']))>5:reasons.append('old_source_coordinate_candidate_over_5km')
   if unique_counts.get((b.census_year,w['former_name'],b.region_norm,a.d),0)>0:reasons.append('former_name_still_separate_same_year_locality')
   if ap and bp:
    dist=distance_km((ap['latitude'],ap['longitude']),(bp['latitude'],bp['longitude']))
    if dist>5:reasons.append('accepted_points_over_5km')
   if aid in state.conflicting_point_targets or bid in state.conflicting_point_targets:reasons.append('accepted_point_conflict')
   if not bp:reasons.append('no_current_accepted_own_locality_point')
   else:
    pts=json.loads(c['points_json']);near=min([distance_km((bp['latitude'],bp['longitude']),(v['latitude'],v['longitude'])) for v in pts] or [999])
    if near>5:reasons.append('current_point_not_confirmed_by_own_entity_P625')
   row={**w,'from_source_record_id':aid,'from_year':int(a.census_year),'from_name':a.settlement_name,'from_district_raw':a.district_raw,'from_population':a.population,'to_source_record_id':bid,'to_year':int(b.census_year),'to_name':b.settlement_name,'to_district_raw':b.district_raw,'to_population':b.population,'region_norm':b.region_norm,'relation':'same_place','decision_status':'candidate_only','admission_allowed':False,'county_transfer_secondary_witness':transfer,'accepted_point_distance_km':dist,'current_native_code':c['source_oktmo_exact_digits'],'current_P764_witness':c['wikidata_truthy_exact_p764_claims_json'],'current_P131_witness':c['wikidata_truthy_p131_claims_json'],'current_P625_witness':c['wikidata_truthy_p625_claims_json'],'current_own_label_witness':c['wikidata_tsv_ru_labels_json'],'boundary_comparability_asserted':False,'reason':';'.join(reasons),'eligible_for_root_review':not reasons}
   (holds if reasons else rows).append(row)
R=pd.DataFrame(rows);H=pd.DataFrame(holds);R.to_csv(OUT/'candidate_identity_edges.csv',index=False);(OUT/'own_article_context_witnesses.json.gz').write_bytes(gzip.compress(json.dumps({q:v for q,v in articleproof.items() if q in {r['qid'] for r in rows}|{'Q1873736','Q4230262'}},ensure_ascii=False).encode(),mtime=0));H.to_csv(OUT/'held_candidate_pairs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
# Simulate eligible edges and explicit accepted-point continuity locally only.
points=[];simulation_conflicts=[]
for r in sorted(rows,key=lambda r:-max(r['from_population'],r['to_population'])):
 a,b=r['from_source_record_id'],r['to_source_record_id']
 try:state.union(a,b)
 except ValueError as e:simulation_conflicts.append({'from_source_record_id':a,'to_source_record_id':b,'reason':str(e)});continue
 donor=state.point_rows[b]
 for sid in [a,b]:
  if sid not in state.point_rows:
   p=dict(target_source_record_id=sid,target_year=int(state.by_id.loc[sid,'census_year']),latitude=donor['latitude'],longitude=donor['longitude'],coordinate_source_record_id=b,coordinate_admission_status='candidate_only',admission_allowed=False,coordinate_origin_ledger=donor['point_ledger_path'],coordinate_origin_ledger_sha256=sha(Path(donor['point_ledger_path'])),coordinate_origin_ledger_locator='target_source_record_id='+b,admission_rule='own_entity_exact_former_name_explicit_county_secondary_context_point_continuity',direct_historical_coordinate_measurement=False,boundary_comparability_asserted=False,qid=r['qid']);points.append(p);state.point_rows[sid]=p
pd.DataFrame(points,columns=list(points[0]) if points else ['target_source_record_id','coordinate_admission_status']).to_csv(OUT/'candidate_point_uses.csv',index=False)
after=state.metrics();sample=R.sample(min(20,len(R)),random_state=20261007) if len(R) else R;sample.to_csv(OUT/'fixed_sample20.csv',index=False)
top=R.assign(mass=R[['from_population','to_population']].max(axis=1)).sort_values('mass',ascending=False).head(5) if len(R) else R;top.to_csv(OUT/'top5_raw_checks.csv',index=False)
summary=dict(status='candidate_only_no_admissions',loader_stage=11,cached_and_bounded_live_own_entity_witnesses=len(W),unique_candidate_pairs=len(seen),already_connected_filtered=already,eligible_edges=len(rows),held_pairs=len(holds),candidate_point_uses=len(points),simulation_conflicts=simulation_conflicts,baseline=baseline,simulated_after=after,net_new_full3_population={y:after[y]['covered_population']-baseline[y]['covered_population'] for y in baseline},inputs=inputs,held_reason_counts=dict(Counter(r['reason'] for r in holds)),sample_seed=20261007,sample_size=len(sample),top5_size=len(top),primary_legal_rename_verified=False,secondary_admin_transfer_supported=True,source_population_values_modified=False)
(OUT/'run_receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs','baseline','simulated_after']},ensure_ascii=False,indent=2))
