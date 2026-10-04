"""Raw-row validation of selected 2002/2010 source-order context candidates.

The result is review-ready evidence only. It does not accept identity edges or
transfer an unknown 2010 district value into the selected source data.
"""
from __future__ import annotations
import hashlib, json, re, sys, random
from collections import defaultdict
from pathlib import Path
import duckdb
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from research_rebuild.mass_linkage.apply_identity_rules import _source_label_key,_source_region_key,_district_key

F=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
INPUT_MANIFEST=Path('/workspace/settlements-baseline/output/input_manifest.csv')
BASE=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_extensions')
PREV=Path('/workspace/settlements-work/continuation_20261004/root/R4/source_order_context_diagnostic')
RAW=Path('/workspace/settlements-raw')
RAW_FALLBACK=Path('/workspace/settlements-work/sources/r2-missing')
OUT=Path('/workspace/settlements-work/continuation_20261004/root/R4/source_order_context_review_ready')
STATUSES={'checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific'}
TYPE_PREFIX={
 'город':r'(?:город|г\.)','посёлок':r'(?:пос[её]лок|п\.)','поселок':r'(?:пос[её]лок|п\.)','рабочий посёлок':r'(?:рабочий пос[её]лок|рп\.)','пгт':r'(?:пгт|пос[её]лок городского типа)',
 'село':r'(?:село|с\.)','деревня':r'(?:деревня|д\.)','хутор':r'(?:хутор|х\.)','станица':r'(?:станица|ст-?ца\.?|ст\.)',
 'аул':r'(?:аул|а\.)','аал':r'(?:аал)','арбан':r'(?:арбан)','выселок':r'(?:выселок)','слобода':r'(?:слобода|сл\.)','кишлак':r'(?:кишлак|киш\.)','местечко':r'(?:местечко|м\.)','мест.':r'(?:мест\.?|местечко)',
 'заимка':r'(?:заимка|з\.)','сельское поселение':r'(?:сельское поселение)','городское поселение':r'(?:городское поселение)',
 'станция':r'(?:станция|ст\.)','железнодорожная казарма':r'(?:железнодорожная казарма)','железнодорожный объект':r'(?:железнодорожная казарма|железнодорожный объект)','платформа':r'(?:платформа|платф\.)',
 'кордон':r'(?:кордон)','мыза':r'(?:мыза)','посёлок городского типа':r'(?:пос[её]лок городского типа|пгт)','населённый пункт':r'(?:насел[её]нный пункт)',
 'починок':r'(?:починок|поч\.)','разъезд':r'(?:разъезд|раз\.)','улус':r'(?:улус)','участок':r'(?:участок)','кишлак':r'(?:кишлак|киш\.)',
}
TYPE_RE=re.compile(r'^\s*('+'|'.join(sorted(set(TYPE_PREFIX.values()),key=len,reverse=True))+r')\s*',re.I)
TYPE_CANON={_source_label_key(k):k for k in TYPE_PREFIX}
AGG_SCOPES={'federal_city_region','municipality','municipal_aggregate','region','administrative_area','territorial_aggregate'}

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def txt(v): return '' if v is None or pd.isna(v) else str(v).strip()
def token(r): return (_source_label_key(r.settlement_name),_source_label_key(r.settlement_type))
def district_stems(value):
 words=_district_key(value).split()
 return {re.sub(r'(?:ского|цкого|ской|цкой|ский|цкий|ого|его|ому|ему|ая|яя|ое|ее|ый|ий|ой)$','',w) for w in words if w not in {'район','района','округ','округа','сельсоветы','сельский','городской'}}
def district_context_matches(expected,label):
 a=district_stems(expected);b=district_stems(label)
 return bool(a and b and a.issubset(b))
def raw_path(rel):
 p=RAW/str(rel)
 if p.is_file():return p
 b=Path(str(rel)).name
 for alt in {'murmansk_population.doc':'murmansk_population.doc','kaliningrad_tom1.xlsx':'kaliningrad_tom1.xlsx','arkhangelsk_2010_archived_original.html':'arkhangelsk_2010_archived_original.html'}:
  if b==alt:
   q=RAW_FALLBACK/alt
   if q.is_file():return q
 return p
def parse_type_label(label,expected_type):
 s=txt(label)
 typ=txt(expected_type).casefold().replace('ё','е')
 alias=TYPE_PREFIX.get(typ)
 if not alias:return False,'unrecognized_selected_type'
 m=re.match(r'^\s*'+alias+r'\s*',s,re.I)
 if not m:return False,'raw_type_prefix_mismatch'
 return True,''
def num(v):
 if v is None or pd.isna(v):return None
 try:
  x=float(str(v).replace(' ','').replace('\xa0','').replace(',','.'))
 except (ValueError,TypeError):return None
 return int(x) if x.is_integer() else x
def json_cells(row):
 out=[]
 for v in row.tolist():
  if v is None or pd.isna(v):out.append(None)
  elif isinstance(v,(int,float)):
   x=float(v);out.append(int(x) if x.is_integer() else x)
  else:out.append(str(v))
 return out
def population_header(df,year,namecol=None):
 matches=[]
 for i in range(min(40,len(df))):
  row=df.iloc[i]
  for col,v in enumerate(row.tolist()):
   k=_source_label_key(v)
   if not k:continue
   if year==2002 and ('численность' in k or k=='население'):
    matches.append((i,col,k))
   elif year==2010 and (k=='всего' or k in {'все население','численность населения','численность'}):
    matches.append((i,col,k))
 if namecol is not None:matches=[x for x in matches if x[1]>namecol]
 if not matches:return None
 minrow=min(x[0] for x in matches)
 same=[x for x in matches if x[0]==minrow]
 if namecol is not None:same.sort(key=lambda x:(x[1]-namecol,x[1]))
 else:same.sort(key=lambda x:x[1])
 return same[0]

def main():
 if OUT.exists() and any(OUT.iterdir()): raise FileExistsError(OUT)
 OUT.mkdir(parents=True,exist_ok=True)
 selected=F/'selected_observations.parquet'; evidence=F/'source_evidence.parquet'; graph=BASE/'accepted_identity_edges.parquet'
 source_paths={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [selected,evidence,graph,INPUT_MANIFEST]}
 manifest=pd.read_csv(INPUT_MANIFEST).set_index('path')
 manifest_hash={str(k):txt(v) for k,v in manifest.sha256.items()}
 c=duckdb.connect()
 s=c.execute(f"""select source_record_id,census_year,settlement_name,settlement_type,region_raw,district_raw,municipality_raw,population,population_scope,population_value_quality,source_file,source_sheet,source_row,source_native_id,source_name_raw,source_population_raw,source_sha256,source_locator,entity_grain_status,is_additive_settlement_record from read_parquet('{selected}') where census_year in (2002,2010)""").df()
 ev=c.execute(f"""select source_record_id,census_year,source_evidence_json,json_extract_string(source_evidence_json,'$.legacy_identity_reasons') legacy_identity_reasons,lower(coalesce(json_extract_string(source_evidence_json,'$.is_federal_aggregate'),'false'))='true' is_federal_aggregate,lower(coalesce(json_extract_string(source_evidence_json,'$.legacy_same_year_collision'),'false'))='true' legacy_same_year_collision,nullif(json_extract_string(source_evidence_json,'$.legacy_verified_successor_settlement_id'),'') successor,lower(coalesce(json_extract_string(source_evidence_json,'$.is_additive_settlement_record'),'false'))='true' is_additive from read_parquet('{evidence}') where census_year=2010""").df().set_index('source_record_id',drop=False)
 g=c.execute(f"""select decision_id,relation,from_source_record_id,try_cast(from_year as int) from_year,to_source_record_id,try_cast(to_year as int) to_year,decision_status,decision_rule,review_id,review_sha256,evidence_uri,evidence_sha256,application_review_id,application_review_sha256 from read_parquet('{graph}')""").df()
 g=g[(g.relation=='same_place')&g.decision_status.isin(STATUSES)&g.from_year.isin([2002,2010])&g.to_year.isin([2002,2010])&(g.from_year!=g.to_year)].copy()
 g['id02']=g.apply(lambda r:r.from_source_record_id if r.from_year==2002 else r.to_source_record_id,axis=1);g['id10']=g.apply(lambda r:r.from_source_record_id if r.from_year==2010 else r.to_source_record_id,axis=1)
 s['region_key']=s.region_raw.map(_source_region_key);s['name_key']=s.settlement_name.map(_source_label_key);s['type_key']=s.settlement_type.map(_source_label_key);s['source_row_num']=pd.to_numeric(s.source_row,errors='coerce')
 s=s.dropna(subset=['source_row_num']).copy(); sx=s.set_index('source_record_id',drop=False)
 edge_lookup=defaultdict(list)
 for e in g.itertuples(index=False): edge_lookup[(str(e.id02),str(e.id10))].append(e)
 align=pd.read_csv(PREV/'accepted_anchor_source_order_alignment.csv')
 runs=pd.read_csv(PREV/'anchored_exact_name_run_context_candidates.csv')
 eligible=align[(align.accepted_anchor_count>=50)&(align.kendall_order_tau>=.95)].copy()
 runs=runs.merge(eligible[['region_key','source_file_2002','source_file_2010','accepted_anchor_count','kendall_order_tau']],on=['region_key','source_file_2002','source_file_2010'],how='inner')
 # Assign all whole-list source rows and compute every exact 5-token vector
 # occurrence, not just the rows already emitted as anchored candidates.
 cohorts=set(ev.loc[ev.legacy_identity_reasons.eq('["ordinal_historical_identifier_hypothesis"]'),'source_record_id'].astype(str))
 candidates=[]
 for (region,f02,f10),grp in runs.groupby(['region_key','source_file_2002','source_file_2010']):
  # The requested witness is the coded regional-list family. Parallel official
  # census tables are a different publication and cannot create or break this
  # source-list vector uniqueness check.
  province02=s[(s.census_year==2002)&(s.region_key==region)&s.source_file.astype(str).str.startswith('data/raw/2002/')]
  all02={file:g.sort_values('source_row_num').reset_index(drop=True) for file,g in province02.groupby('source_file')}
  all02windows={}
  for f,g in all02.items():
   ks=list(zip(g.name_key,g.type_key));wi=defaultdict(list)
   for j in range(len(ks)-4):
    tt=tuple(ks[j:j+5])
    if all(n and ty for n,ty in tt):wi[tt].append(j)
   all02windows.update({(f,tt):js for tt,js in wi.items()})
  d02=all02.get(f02,pd.DataFrame())
  d10=s[(s.census_year==2010)&(s.region_key==region)&(s.source_file==f10)].sort_values('source_row_num').reset_index(drop=True)
  if len(d02)<5 or len(d10)<5:continue
  keys02=list(zip(d02.name_key,d02.type_key));keys10=list(zip(d10.name_key,d10.type_key))
  windows02=defaultdict(list);windows10=defaultdict(list)
  for j in range(len(keys02)-4):
   t=tuple(keys02[j:j+5])
   if all(n and ty for n,ty in t):windows02[t].append(j)
  for i in range(len(keys10)-4):
   t=tuple(keys10[i:i+5])
   if all(n and ty for n,ty in t):windows10[t].append(i)
  focal_ids={str(x) for x in grp.focal_2010_id if str(x) in cohorts}
  # For every focal source row, examine all possible source-order windows and
  # collect its target mapping vector across the complete selected province list.
  for sid10 in focal_ids:
   hit10=[i for i,x in enumerate(d10.source_record_id.astype(str)) if x==sid10]
   target_ids=set(); proofruns=[]
   matched_tokens=set()
   for ix10 in hit10:
    for start10 in range(max(0,ix10-4),min(ix10+1,len(keys10)-4)):
     tok=tuple(keys10[start10:start10+5])
     for fother in all02:
      for start02all in all02windows.get((fother,tok),[]):
       other=all02[fother]
       target_ids.add(str(other.source_record_id.iloc[start02all+(ix10-start10)]))
     for start02 in windows02.get(tok,[]):
      pairs=[(str(d02.source_record_id.iloc[start02+k]),str(d10.source_record_id.iloc[start10+k])) for k in range(5)]
      nanchor=sum(bool(edge_lookup.get(p)) for p in pairs)
      if nanchor<2:continue
      target=pairs[ix10-start10][0];target_ids.add(target)
      drows=d02.iloc[start02:start02+5]
      districts={_district_key(x) for x in drows.district_raw if txt(x)}
      proofruns.append({'start02':start02,'start10':start10,'target02':target,'nanchor':nanchor,'districts':districts,'pairs':pairs})
   if not target_ids:continue
   chosen=max(proofruns,key=lambda z:(z['nanchor'],-z['start02']))
   focal=sx.loc[sid10];target=sx.loc[chosen['target02']]
   if isinstance(focal,pd.DataFrame) or isinstance(target,pd.DataFrame):continue
   fev=ev.loc[sid10]
   flags=[]
   if bool(fev.is_federal_aggregate):flags.append('federal_aggregate')
   if bool(fev.legacy_same_year_collision):flags.append('same_year_collision')
   if txt(fev.successor):flags.append('successor_event')
   if not bool(fev.is_additive):flags.append('not_additive_settlement')
   if txt(focal.population_scope) in AGG_SCOPES:flags.append('aggregate_population_scope')
   if len(target_ids)!=1:flags.append('whole_province_target_ambiguous')
   if len(chosen['districts'])!=1:flags.append('2002_five_row_run_not_single_printed_district')
   district=txt(target.district_raw)
   if not district or _district_key(district) not in chosen['districts']:flags.append('target_2002_district_context_missing_or_inconsistent')
   pairrows=[]
   for p in chosen['pairs']:
    es=edge_lookup.get(p,[])
    if es:
     e=es[0];pairrows.append({'from_2002':p[0],'to_2010':p[1],'decision_id':e.decision_id,'decision_status':e.decision_status,'decision_rule':e.decision_rule,'review_id':e.review_id,'review_sha256':e.review_sha256,'evidence_uri':e.evidence_uri,'evidence_sha256':e.evidence_sha256,'application_review_id':e.application_review_id,'application_review_sha256':e.application_review_sha256})
   if len(pairrows)<2:flags.append('accepted_anchor_count_under_two')
   candidates.append({'candidate_family':'source_order_2002_2010_exact_five_typed_name_context','candidate_rule':'unique whole-coded-province five-name/type vector with >=2 existing accepted anchor edges; same verified printed 2002 county across target run','region_key':region,'source_file_2002':f02,'source_sheet_2002':target.source_sheet,'source_row_2002':int(target.source_row_num),'source_locator_2002':txt(target.source_locator),'source_sha256_2002_selected':txt(target.source_sha256),'source_id_2002':str(target.source_record_id),'source_file_2010':f10,'source_sheet_2010':focal.source_sheet,'source_row_2010':int(focal.source_row_num),'source_locator_2010':txt(focal.source_locator),'source_sha256_2010_selected':txt(focal.source_sha256),'source_id_2010':sid10,'candidate_population_2010':None if pd.isna(focal.population) else int(focal.population),'target_population_2002':None if pd.isna(target.population) else int(target.population),'district_raw_2010_preserved':txt(focal.district_raw),'population_scope_2010':txt(focal.population_scope),'population_quality_2010':txt(focal.population_value_quality),'entity_grain_2010':txt(focal.entity_grain_status),'additive_2010':bool(fev.is_additive),'federal_aggregate_2010':bool(fev.is_federal_aggregate),'same_year_collision_2010':bool(fev.legacy_same_year_collision),'successor_event_2010':txt(fev.successor),'whole_province_matching_2002_target_count':len(target_ids),'whole_province_target_ids_json':json.dumps(sorted(target_ids),ensure_ascii=False),'candidate_context_window_occurrences':len(proofruns),'selected_context_start_2002_row':int(d02.source_row_num.iloc[chosen['start02']]),'selected_context_start_2010_row':int(d10.source_row_num.iloc[chosen['start10']]),'selected_context_accepted_anchor_count':chosen['nanchor'],'kendall_order_tau':float(grp.kendall_order_tau.iloc[0]),'true_2002_district_raw':district,'five_row_2002_districts_json':json.dumps(sorted(chosen['districts']),ensure_ascii=False),'anchor_decision_paths_json':json.dumps(pairrows,ensure_ascii=False),'preliminary_reason':'|'.join(flags) if flags else 'candidate_requires_raw_sample_review','identity_admitted':False})
 cand=pd.DataFrame(candidates)
 if cand.empty:raise ValueError('No candidates in high-anchor/high-order source pairs')
 # Collapse overlapping windows and parallel accepted edges into one candidate
 # per 2010 source row, unioning every possible target across all coded lists.
 collapsed=[]
 for sid,grp in cand.groupby('source_id_2010',sort=False):
  best=grp.sort_values(['selected_context_accepted_anchor_count','kendall_order_tau'],ascending=False).iloc[0].to_dict()
  alltargets=set()
  for val in grp.whole_province_target_ids_json:
   alltargets.update(json.loads(val))
  best['whole_province_target_ids_json']=json.dumps(sorted(alltargets),ensure_ascii=False)
  best['whole_province_matching_2002_target_count']=len(alltargets)
  if len(alltargets)!=1:
   prior=best['preliminary_reason']
   best['preliminary_reason']='|'.join(x for x in [prior,'whole_province_target_ambiguous'] if x and x!='candidate_requires_raw_sample_review')
  collapsed.append(best)
 cand=pd.DataFrame(collapsed)
 # Risk-aware fixed 100 sample: 34 largest population, 33 exact-name/type
 # homonym keys, 33 seeded sample spanning source pairs and hazard flags.
 rs=random.Random(20261004); selected_samples=[]
 cand['sample_stratum']=''
 cand['homonym_2002_count']=0
 byprov={(r,f):g for (r,f),g in s[s.census_year.eq(2002)].groupby(['region_key','source_file'])}
 for i,r in cand.iterrows():
  grp=byprov.get((r.region_key,r.source_file_2002),pd.DataFrame())
  t=sx.loc[r.source_id_2002]
  cand.loc[i,'homonym_2002_count']=int(((grp.name_key==t.name_key)&(grp.type_key==t.type_key)).sum()) if len(grp) else 0
 pool=cand.drop_duplicates('source_id_2010').copy()
 def take(df,n,label,score=None):
  nonlocal selected_samples
  ids=set(x['source_id_2010'] for x in selected_samples)
  sub=df[~df.source_id_2010.isin(ids)]
  if score:sub=sub.sort_values(score,ascending=False)
  elif len(sub):sub=sub.sample(frac=1,random_state=20261004+len(selected_samples))
  for _,rr in sub.head(n).iterrows():
   selected_samples.append({'source_id_2010':rr.source_id_2010,'sample_stratum':label})
 take(pool,34,'high_population','candidate_population_2010')
 take(pool[pool.homonym_2002_count.gt(1)],33,'homonym_risk','candidate_population_2010')
 risk=pool[pool.preliminary_reason.ne('candidate_requires_raw_sample_review') | pool.homonym_2002_count.gt(1)]
 take(risk,33,'risk_block_seeded')
 if len(selected_samples)<100:take(pool,100-len(selected_samples),'province_pair_seeded')
 sample=pd.DataFrame(selected_samples[:100])
 if len(sample)<100:raise ValueError(f'Only {len(sample)} unique focal rows available for fixed sample')
 cand=cand.merge(sample,on='source_id_2010',how='left',suffixes=('','_sample'))
 cand['sample_stratum']=cand.sample_stratum.fillna('not_sampled')
 # Raw sheet reads and SHA values are cached once for each source file.
 hash_cache={}; sheet_cache={}; rawmeta={}
 def raw_file(rel):
  if rel not in rawmeta:
   p=raw_path(rel)
   if p.is_file():
    actual=sha(p); expected_manifest=manifest_hash.get(str(rel),'')
    rawmeta[rel]={'path':str(p),'sha256':actual,'bytes':p.stat().st_size,'manifest_sha256':expected_manifest,'matches_input_manifest':bool(expected_manifest and actual==expected_manifest),'exists':True}
   else:rawmeta[rel]={'path':str(p),'exists':False}
  return Path(rawmeta[rel]['path']) if rawmeta[rel]['exists'] else None
 def sheet(rel,sh):
  key=(rel,str(sh))
  if key not in sheet_cache:
   p=raw_file(rel)
   if p is None:sheet_cache[key]=None
   else:sheet_cache[key]=pd.read_excel(p,sheet_name=sh,header=None,dtype=object)
  return sheet_cache[key]
 sample_rows=[]
 cand_by_id={r.source_id_2010:r for r in cand.itertuples(index=False)}
 for sm in sample.itertuples(index=False):
  row=cand_by_id[sm.source_id_2010]
  i02=sx.index.get_loc(row.source_id_2002);i10=sx.index.get_loc(row.source_id_2010)
  a=sx.loc[row.source_id_2002];b=sx.loc[row.source_id_2010]
  d02=s[(s.census_year==2002)&(s.region_key==row.region_key)&(s.source_file==row.source_file_2002)].sort_values('source_row_num').reset_index(drop=True)
  d10=s[(s.census_year==2010)&(s.region_key==row.region_key)&(s.source_file==row.source_file_2010)].sort_values('source_row_num').reset_index(drop=True)
  pos02=int(d02.index[d02.source_record_id.eq(row.source_id_2002)][0]);pos10=int(d10.index[d10.source_record_id.eq(row.source_id_2010)][0])
  run=cand[(cand.source_id_2010==row.source_id_2010)&(cand.source_file_2002==row.source_file_2002)].iloc[0]
  st02=int(run.selected_context_start_2002_row);st10=int(run.selected_context_start_2010_row)
  win02=d02[(d02.source_row_num>=st02)].head(5).copy();win10=d10[(d10.source_row_num>=st10)].head(5).copy()
  raw_reports=[];hdr=[]
  for year,win,rel,sh in [(2002,win02,row.source_file_2002,row.source_sheet_2002),(2010,win10,row.source_file_2010,row.source_sheet_2010)]:
   df=sheet(rel,sh)
   if df is None:raw_reports.append({'year':year,'status':'raw_source_missing','source_file':rel});continue
   for rr in win.itertuples(index=False):
    rn=int(rr.source_row_num);raw=df.iloc[rn-1] if rn-1<len(df) else None
    if raw is None:raw_reports.append({'year':year,'source_record_id':rr.source_record_id,'source_row':rn,'status':'raw_row_missing'});continue
    expected_label=txt(rr.source_name_raw)
    matching_cols=[q for q,v in enumerate(raw.tolist()) if _source_label_key(v)==_source_label_key(expected_label)]
    namecol=matching_cols[0] if len(matching_cols)==1 else None
    lab=txt(raw.iloc[namecol]) if namecol is not None else ''
    popspec=population_header(df,year,namecol)
    popheadrow,popcol_actual,popheadtext=popspec if popspec else (None,None,'')
    pv=raw.iloc[popcol_actual] if popcol_actual is not None else None
    name_ok=_source_label_key(lab)==_source_label_key(rr.source_name_raw)
    type_ok,_=parse_type_label(lab,rr.settlement_type)
    pop=num(pv); expected=None if pd.isna(rr.population) else int(rr.population)
    pop_status='raw_population_matches_selected' if pop is not None and expected==pop else ('raw_population_header_missing' if popspec is None else ('raw_population_suppressed' if pop is None else 'raw_population_mismatch'))
    grain_ok=bool(rr.is_additive_settlement_record) and txt(rr.population_scope) not in AGG_SCOPES and bool(txt(rr.settlement_type))
    row_status='pass' if name_ok and type_ok and pop_status=='raw_population_matches_selected' and grain_ok else 'hold'
    filepin=rawmeta.get(rel,{})
    selected_sha=txt(rr.source_sha256)
    selectedsha_ok=(not selected_sha) or selected_sha==filepin.get('sha256')
    filehashmatch=bool(filepin.get('matches_input_manifest') and selectedsha_ok)
    raw_reports.append({'year':year,'source_record_id':rr.source_record_id,'row':rn,'raw_name_column_index':namecol,'raw_label':lab,'source_name_raw':rr.source_name_raw,'selected_name_type':f'{rr.settlement_type} {rr.settlement_name}','label_exact_raw_name_pass':bool(name_ok),'raw_type_prefix_pass':bool(type_ok),'population_column_header_row_1based':None if popheadrow is None else popheadrow+1,'population_column_index':popcol_actual,'population_column_header':popheadtext,'population_header_cells_json':json.dumps(json_cells(df.iloc[popheadrow]) if popheadrow is not None else [],ensure_ascii=False),'raw_population_cell':txt(pv),'selected_population':expected,'raw_population_status':pop_status,'population_quality':txt(rr.population_value_quality),'population_scope':txt(rr.population_scope),'entity_grain_status':txt(rr.entity_grain_status),'record_grain_check_pass':grain_ok,'is_additive':bool(rr.is_additive_settlement_record),'raw_row_all_cells_json':json.dumps(json_cells(raw),ensure_ascii=False),'actual_source_file_sha256':filepin.get('sha256'),'input_manifest_sha256':filepin.get('manifest_sha256'),'raw_sha256_matches_manifest':bool(filepin.get('matches_input_manifest')),'selected_source_sha256':selected_sha or None,'source_sha256_matches_selected':None if not selected_sha else selectedsha_ok,'status':row_status if filehashmatch else 'hold_source_sha_mismatch'})
    if year==2002:
     hdr.append({'source_record_id':rr.source_record_id,'source_row':rn,'district_raw':txt(rr.district_raw),'municipality_raw':txt(rr.municipality_raw),'raw_previous_hierarchy_cells':[]})
     # Search only the pinned raw prefix for a printed county/district label.
     # The line must occur before the locality row, and the expected county
     # token must appear in that actual printed text.
     dk=_district_key(rr.district_raw)
     for q in range(0,rn-1):
      labels=[txt(v) for v in df.iloc[q].tolist() if txt(v)]
      for label in labels:
       if 'район' in _source_label_key(label) and dk and district_context_matches(rr.district_raw,label):
        hdr[-1]['raw_previous_hierarchy_cells'].append({'row':q+1,'text':label})
     hdr[-1]['raw_previous_hierarchy_cells']=hdr[-1]['raw_previous_hierarchy_cells'][-3:]
     latest=[]
     for q in range(0,rn-1):
      labels=[txt(v) for v in df.iloc[q].tolist() if txt(v)]
      labels=[label for label in labels if 'район' in _source_label_key(label)]
      if labels:latest=[{'row':q+1,'text':' | '.join(labels),'cells':json_cells(df.iloc[q])}]
     hdr[-1]['nearest_printed_district_heading']=latest
     hdr[-1]['printed_district_header_pass']=bool(latest and dk and district_context_matches(rr.district_raw,latest[-1]['text']))
  checkall=all(x['status']=='pass' for x in raw_reports) and len(raw_reports)==10
  districts={_district_key(x['district_raw']) for x in hdr if x['district_raw']}
  hdr_ok=len(hdr)==5 and len(districts)==1 and all(x['printed_district_header_pass'] for x in hdr)
  anchor_decisions=json.loads(row.anchor_decision_paths_json)
  sample_rows.append({'sample_stratum':sm.sample_stratum,'source_id_2010':row.source_id_2010,'source_id_2002':row.source_id_2002,'raw_five_rows_2010_and_2002_pass':checkall,'five_2002_rows_same_nonempty_district':hdr_ok,'printed_district_headers':json.dumps(hdr,ensure_ascii=False),'raw_five_row_evidence_json':json.dumps(raw_reports,ensure_ascii=False),'anchor_decision_paths_json':json.dumps(anchor_decisions,ensure_ascii=False),'source_sha256_2002_selected':txt(a.source_sha256),'source_sha256_2010_selected':txt(b.source_sha256),'population_value_quality_2010':txt(b.population_value_quality),'population_scope_2010':txt(b.population_scope),'raw_district_2010_preserved':txt(b.district_raw),'sample_status':'candidate_only_for_root_independent_review' if checkall and hdr_ok else 'hold_raw_context_or_row_check'})
 sampledf=pd.DataFrame(sample_rows)
 sampledf.to_csv(OUT/'fixed_100_raw_context_review.csv',index=False)
 cand.to_csv(OUT/'whole_province_unique_context_candidates.csv',index=False)
 # Source hashes are byte-pinned once per physical workbook, including fallback
 # files under sources/r2-missing where the raw mirror lacks a source.
 source_hash_rows=[{'source_file':k,**v} for k,v in sorted(rawmeta.items())]
 pd.DataFrame(source_hash_rows).to_csv(OUT/'raw_source_hashes.csv',index=False)
 summary={'status':'bounded_raw_context_validation_candidate_only','candidate_identity_admissions':0,'focal_candidates_in_high_anchor_high_order_groups':int(cand.source_id_2010.nunique()),'distinct_focal_candidate_population':int(cand.drop_duplicates('source_id_2010').candidate_population_2010.fillna(0).sum()),'whole_province_unique_target_rows':int(cand.drop_duplicates('source_id_2010').whole_province_matching_2002_target_count.eq(1).sum()),'whole_province_ambiguous_target_rows':int(cand.drop_duplicates('source_id_2010').whole_province_matching_2002_target_count.gt(1).sum()),'whole_province_target_population_unique':int(cand.drop_duplicates('source_id_2010').loc[lambda x:x.whole_province_matching_2002_target_count.eq(1),'candidate_population_2010'].fillna(0).sum()),'rows_with_aggregate_event_collision_holds':int(cand.drop_duplicates('source_id_2010').preliminary_reason.str.contains('aggregate|collision|successor|not_additive',case=False,regex=True).sum()),'rows_with_single_2002_printed_district_context':int(cand.drop_duplicates('source_id_2010').five_row_2002_districts_json.map(lambda x:len(json.loads(x))==1).sum()),'sample_size':len(sampledf),'sample_raw_five_row_pass':int(sampledf.raw_five_rows_2010_and_2002_pass.sum()),'sample_single_district_printed_header_pass':int(sampledf.five_2002_rows_same_nonempty_district.sum()),'sample_full_context_pass':int((sampledf.raw_five_rows_2010_and_2002_pass&sampledf.five_2002_rows_same_nonempty_district).sum()),'sample_strata':sampledf.sample_stratum.value_counts().to_dict(),'source_files':source_hash_rows,'inputs':source_paths,'outputs':{},'limitations':['The 2010 source district remains as selected, including null; 2002 printed historical district context is carried as a candidate relation inference only.','No ordinal/native code was used to choose a target. The frozen selected rows provide the whole-province typed-name vector; raw workbooks were re-read for the fixed sample.','Current graph anchors are accepted same_place edges, but each candidate still requires independent root review and anchor context approval.']}
 for p in sorted(OUT.iterdir()):summary['outputs'][p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
 summary['builder_sha256']=sha(Path(__file__))
 (OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
