import json,gzip,re
from pathlib import Path
import pandas as pd
O=Path(__file__).parent
T=pd.read_csv(O.parent/'native_rural_type_alias_mass_20261008/discovery_ranked_rural_class_changes.csv.gz');T=T[T.outcome.eq('no_literal_old_native_name')]
# Name pool limits entity witnesses to the unresolved native2010 targets' names; final admission requires exact code-bound current source-ID entity.
names=set(T.name.str.lower());W=pd.read_parquet('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');W=W[W.wikidata_name_exact_label & ~W.entity_competition_across_tsv_or_truthy & ~W.source_observation_competition_for_exact_oktmo];rows=[];qids=set(W.wikidata_qid);files=list(Path('/workspace/settlements-raw/data/raw/wikidata_entities_full').glob('batch*.json.gz'))
for p in files:
 d=json.load(gzip.open(p,'rt'));es=d.get('payload',d).get('entities',{})
 for q,e in es.items():
  if q not in qids:continue
  label=e.get('labels',{}).get('ru',{}).get('value','')
  if label.lower() not in names:continue
  for n,a in enumerate(e.get('aliases',{}).get('ru',[])):rows.append({'qid':q,'current_label':label,'alias':a['value'],'witness_kind':'own_entity_ru_alias','witness_file':str(p),'witness_locator':f'payload.entities.{q}.aliases.ru[{n}]','raw_witness_json':json.dumps(a,ensure_ascii=False)})
  for prop in ['P1448','P2561','P1705']:
   for c in e.get('claims',{}).get(prop,[]):
    v=c.get('mainsnak',{}).get('datavalue',{}).get('value',{})
    if isinstance(v,dict) and v.get('language')=='ru':rows.append({'qid':q,'current_label':label,'alias':v.get('text',''),'witness_kind':'own_entity_'+prop,'witness_file':str(p),'witness_locator':c.get('id'),'raw_witness_json':json.dumps(c,ensure_ascii=False)})
for p in Path('/workspace/settlements-raw/data/raw/wikipedia_articles').glob('batch*.json.gz'):
 d=json.load(gzip.open(p,'rt'));req={r.get('article_title'):r.get('wikidata_id_effective') for r in d.get('requested',[])};pages=d.get('payload',{}).get('query',{}).get('pages',[])
 for page in (pages if isinstance(pages,list) else pages.values()):
  title=page.get('title','');q=req.get(title)
  if q not in qids or title.split(' (')[0].lower() not in names:continue
  rev=page.get('revisions',[{}])[0];text=rev.get('slots',{}).get('main',{}).get('content','')
  for m in re.finditer(r'^\s*\|\s*прежние (?:имена|названия)\s*=([^\n]+)',text,re.M):
   vals=re.findall(r'\{\{НП-ПН\|([^}]+)',m[1]);aa=[]
   for v in vals:aa += [x.strip() for x in v.split('|') if not re.fullmatch(r'\d{1,4}',x.strip())]
   for a in aa:rows.append({'qid':q,'current_label':title,'alias':a,'witness_kind':'own_article_former_names_infobox','witness_file':str(p),'witness_locator':f'pageid={page.get("pageid")};revid={rev.get("revid")}','raw_witness_json':m[0]})
f=pd.DataFrame(rows);f.to_csv(O/'cached_own_alias_inventory.csv.gz',index=False,compression={'method':'gzip','mtime':0});W[W.wikidata_qid.isin(set(f.qid) if len(f) else set())].to_csv(O/'cached_alias_current_code_bindings.csv.gz',index=False,compression={'method':'gzip','mtime':0});print('alias witnesses',len(f),'QIDs',f.qid.nunique() if len(f) else 0)
