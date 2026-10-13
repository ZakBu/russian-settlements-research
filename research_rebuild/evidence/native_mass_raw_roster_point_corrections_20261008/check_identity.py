"""Hold retrospective point reuse when full raw namesakes lack an own historical parish/source bracket."""
import sys,re,json,collections
from pathlib import Path
import pandas as pd,xlrd,duckdb
O=Path(__file__).parent;sys.path.insert(0,str(O));sys.path.insert(0,'/workspace/russian-settlements-research/research_rebuild/mass_linkage')
from current_chain_state_20261007 import sha,normalize
from apply_unique_county_name_bridge_20261007 import county_key
E=O.parent;f=pd.read_csv(O/'fullraw_own_code_point_recovery_witnesses.csv.gz',keep_default_na=False);cand=pd.read_csv(E/'native_singleton_rural_mass_20261008/positive_literal_native_county_ownpoint_candidates.csv.gz',keep_default_na=False).set_index('native2021_source_record_id');leaves=pd.read_csv(E/'native_singleton_rural_mass_20261008/actual_native_raw_source_checks.csv.gz',keep_default_na=False).set_index('source_record_id');point=pd.read_csv(O/'accepted_point_use_delta.csv.gz',keep_default_na=False);pins={str(p):sha(p) for p in [E/'native_singleton_rural_mass_20261008/positive_literal_native_county_ownpoint_candidates.csv.gz',E/'native_singleton_rural_mass_20261008/actual_native_raw_source_checks.csv.gz',O/'check_identity.py']};rawpath=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');c=duckdb.connect(config={'threads':1});raw=c.execute('select row_number() over() rn,object_level,object_name,oktmo,mun_upper,mun_lower,population from read_parquet(?)',[str(rawpath)]).fetchdf();c.close();idx=collections.defaultdict(list)
def nm(v):return re.sub(r'^(?:село|деревня|пос[её]лок(?: городского типа)?|хутор|станица|аул|город|станция)\s+','',normalize(v))
def parish(v):
 v=normalize(v);v=re.sub(r'\s*[-–—]\s*(?:все|всего|сельское|городское).*$', '',v);v=re.sub(r'^(?:населенные пункты|населённые пункты)\s+','',v);v=re.sub(r'\b(?:сельское поселение|сельское|поселение|сельсовет(?:а)?|сельский совет|сельская администрация|муниципальное образование)\b',' ',v);v=' '.join(re.sub('[^а-яa-z0-9]+',' ',v).split())
 if v.endswith('ское'):v=v[:-2]+'ий'
 if v.endswith('ского'):v=v[:-3]+'ий'
 return v
for z in raw.itertuples():
 if z.object_level=='Населенный пункт' and pd.notna(z.population) and not re.search(r'\(часть\s*\d+\)',z.object_name or '',re.I):idx[(nm(z.object_name),county_key(z.mun_upper))].append(z)
books={};heads={};audit=[];hold=set()
for z in f[f.cohort.eq('source53')&f.point_recovered.astype(str).str.lower().eq('true')].to_dict('records'):
 sid=z['source_record_id'];a=cand.loc[sid];rivals=[r for r in idx[(nm(z['raw_own_label']),county_key(z['raw_own_county']))] if str(r.oktmo)!=str(z['native_own_code'])];intervals=json.loads(a.current_native_two_sided_source_bracket_json);safe_interval=False
 for candidate,l,r,lo,hi in intervals:
  if not any(lo<v.rn<hi for v in rivals):safe_interval=True
 old=a.native2002_source_record_id;leaf=leaves.loc[old];p=Path(leaf.source_file);locator=leaf.source_locator;sheet=locator.split(';row1based=')[0].removeprefix('sheet=');rn=int(locator.rsplit('=',1)[1]);key=(str(p),sheet)
 if key not in heads:
  if str(p) not in books:books[str(p)]=xlrd.open_workbook(str(p),on_demand=True);pins[str(p)]=sha(p)
  sh=books[str(p)].sheet_by_name(sheet);arr=[]
  for i in range(sh.nrows):
   for v in sh.row_values(i):
    if isinstance(v,str) and re.search(r'сельсовет|сельский совет|сельское поселение|сельская администрация',normalize(v)):arr.append((i+1,v,parish(v)))
  heads[key]=arr
 earlier=[v for v in heads[key] if v[0]<rn];header=earlier[-1] if earlier else None;currentparish=parish(z['raw_own_subordinate_context']);sameparish=bool(header and header[2]==currentparish);admit=not rivals or safe_interval or sameparish
 if not admit:hold.add(sid)
 audit.append({'source_record_id':sid,'native2002_source_record_id':old,'historical_source_file':str(p),'historical_source_sha256':pins[str(p)],'historical_source_locator':locator,'nearest_printed_historical_subordinate_caption':header[1] if header else '', 'nearest_printed_historical_subordinate_caption_row':header[0] if header else '', 'current_own_subordinate_caption':z['raw_own_subordinate_context'],'current_own_subordinate_normalized':currentparish,'historical_own_subordinate_normalized':header[2] if header else '', 'fullraw_same_name_county_rivals':len(rivals),'fullraw_rivals_json':json.dumps([v._asdict() for v in rivals],ensure_ascii=False,default=str),'independent_current_source_bracket_excludes_fullraw_rivals':safe_interval,'independent_historical_parish_matches_current_own':sameparish,'historical_point_reuse_identity_held':not admit})
kept=point[~(point.case.isin(hold)&~point.target_source_record_id.str.startswith('2021:'))].copy();kept.to_csv(O/'accepted_point_use_delta.csv.gz',index=False,compression={'method':'gzip','mtime':0,'compresslevel':9});pd.DataFrame(audit).to_csv(O/'recovered_history_fullraw_rival_identity_checks.csv.gz',index=False,compression={'method':'gzip','mtime':0,'compresslevel':9});receipt={'checked_recovered_source53_carriers':len(audit),'historical_point_reuse_identity_holds':len(hold),'held_current_ids':sorted(hold),'removed_retrospective_replacement_uses':len(point)-len(kept),'correct_current_own_point_replacements_retained':True,'input_pins':pins,'output_sha256':sha(O/'recovered_history_fullraw_rival_identity_checks.csv.gz')};(O/'history_fullraw_rival_identity_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='input_pins'},ensure_ascii=False))
