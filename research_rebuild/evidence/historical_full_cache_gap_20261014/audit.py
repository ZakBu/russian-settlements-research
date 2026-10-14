from pathlib import Path
import json,gzip,re,hashlib,collections,unicodedata,math
from decimal import Decimal
import pandas as pd
H=Path(__file__).parent;O=Path('/workspace/shared/historical_full_cache_gap');O.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return ' '.join(unicodedata.normalize('NFKC',str(s or '')).casefold().replace('ё','е').split())
def name(s):return norm(re.sub(r'\s*\([^)]*\)\s*$','',s))
def values(e,k):return [c.get('mainsnak',{}).get('datavalue',{}).get('value') for c in e.get('claims',{}).get(k,[]) if c.get('rank')!='deprecated']
C=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet');L=Path('/workspace/scratch/tochno-np-attach-20261013/native_np_latest_all_attributes.parquet')
core=pd.read_parquet(C);core=core[core.census_year.eq(2021)];latest=pd.read_parquet(L);levels=dict(zip(latest.source_record_id,latest.native_source_object_level));core=core[core.source_record_id.map(levels).eq('Населенный пункт')&~core.region_norm.isin(['крым','севастополь'])];idx=collections.defaultdict(set);by={r['source_record_id']:r for r in core.to_dict('records')}
for sid,r in by.items():
 for k in ['oktmo','okato']:
  v=r.get(k)
  if isinstance(v,str) and re.fullmatch(r'\d{10,11}',v):idx[(k,v)].add(sid)
flat=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_population.tsv');f=pd.read_csv(flat,sep='\t',dtype=str);f=f[f['?date'].str.startswith(('1979-','1989-'),na=False)];flatkeys=set()
for r in f.to_dict('records'):
 y=str(r.get('?date',''))[:4];q=re.search(r'Q\d+',str(r.get('?item')))
 if q and y in ['1979','1989']:
  try:flatkeys.add((q[0],int(y),int(Decimal(str(r['?population'])))))
  except:pass
selected={};pins={str(p):sha(p) for p in [C,L,flat]}
for y in [1979,1989]:
 p=H.parent/'historical_censuses_integration_20261014'/f'population_{y}_selected_long.parquet';d=pd.read_parquet(p);selected[y]=set(d.root);pins[str(p)]=sha(p)
rows=[];entities=[]
for p in sorted(Path('/workspace/settlements-raw/data/raw/wikidata_entities_full').glob('batch_*.json.gz')):
 digest=sha(p);pins[str(p)]=digest
 for q,e in json.load(gzip.open(p))['payload']['entities'].items():
  es=e.get('claims',{});p31=[v.get('id') for v in values(e,'P31') if isinstance(v,dict)];codes=[('oktmo',v) for v in values(e,'P764') if isinstance(v,str)]+[('okato',v) for v in values(e,'P721') if isinstance(v,str)];labels=[v['value'] for v in e.get('labels',{}).values()];pts=[v for v in values(e,'P625') if isinstance(v,dict)];matches=set()
  for code in codes:
   if len(idx[code])==1:matches.update(idx[code])
  binding=None;reason='no_unique_own_native_code'
  if len(matches)==1:
   sid=next(iter(matches));r=by[sid]
   if name(r['settlement_name']) not in {name(s) for s in labels}:reason='literal_name_mismatch'
   elif not r.get('accepted_point_present') or len(pts)!=1:reason='unique_accepted_point_or_source_point_missing'
   else:
    pt=pts[0];km=math.hypot((pt['latitude']-r['accepted_latitude'])*111,(pt['longitude']-r['accepted_longitude'])*111*math.cos(math.radians(pt['latitude'])))
    if km<=5:binding=r;reason='unique_native_own_code_literal_name_current_point_within5km'
    else:reason='point_disagreement'
  for ci,c in enumerate(es.get('P1082',[])):
   for ti,t in enumerate(c.get('qualifiers',{}).get('P585',[])):
    v=t.get('datavalue',{}).get('value',{});date=v.get('time','');m=re.match(r'\+(1979|1989)-',date)
    if not m:continue
    year=int(m[1]);quantity=c.get('mainsnak',{}).get('datavalue',{}).get('value',{});amount=quantity.get('amount');qty=None
    try:
     n=Decimal(amount)
     if n.is_finite() and n>=0 and n==n.to_integral_value():qty=int(n)
    except:pass
    subsets={k:z for k,z in c.get('qualifiers',{}).items() if k!='P585'}
    rows.append(dict(qid=q,year=year,guid=c.get('id'),rank=c.get('rank'),population=qty,quantity_json=json.dumps(quantity,ensure_ascii=False),unit=quantity.get('unit'),date=date,precision=v.get('precision'),qualifiers_json=json.dumps(c.get('qualifiers',{}),ensure_ascii=False),subset_qualifiers_json=json.dumps(subsets,ensure_ascii=False),P31_json=json.dumps(p31),source_file=str(p),source_sha256=digest,source_locator=f"payload.entities.{q}.claims.P1082[{ci}].qualifiers.P585[{ti}]",references_json=json.dumps(c.get('references',[]),ensure_ascii=False),missing_flat_quantity=qty is not None and (q,year,qty) not in flatkeys,anchor_source_record_id=binding['source_record_id'] if binding else None,root=binding['root'] if binding else None,binding_status=reason,already_selected=bool(binding and binding['root'] in selected[year]),current_point_continuity_inference=True,physical_NP_P31_status='raw_types_preserved_not_assumed',primary_census_verification='UNKNOWN'))
d=pd.DataFrame(rows);d.to_parquet(O/'wikidata_full_literal_claims.parquet',index=False)
summary={'full_cache_entities':1450,'literal_full_claims':{str(y):int(d.year.eq(y).sum()) for y in [1979,1989]},'missing_flat_quantity':{str(y):int((d.year.eq(y)&d.missing_flat_quantity).sum()) for y in [1979,1989]},'bound_claims':{str(y):int((d.year.eq(y)&d.root.notna()).sum()) for y in [1979,1989]},'bound_uncovered_roots_candidate_only':{str(y):int(d[d.year.eq(y)&d.root.notna()&~d.already_selected].root.nunique()) for y in [1979,1989]},'P31_counts':d.P31_json.value_counts().to_dict(),'binding_holds':d.binding_status.value_counts().to_dict(),'no_new_downloads':True,'no_coverage_gain_claimed_without_baseline_reproduction':True}
# Full raw Wikipedia inventory bounds year-bearing articles and recognizes supported ordinary numeric year templates.
wiki=collections.Counter();miss=[]
old={1979:pd.read_parquet('/workspace/shared/rsfsr1979_cached_series/wiki/candidate_facts.parquet'),1989:pd.read_parquet(H.parent/'wiki1989_cached_population_20261013/candidate_facts.parquet')}
oldkeys={y:set(zip(z.article_title,z.population.astype(int))) for y,z in old.items()}
for p in sorted(Path('/workspace/shared/wiki1989-cached/data/raw/wikipedia_articles').glob('batch_*.json.gz')):
 pins[str(p)]=sha(p)
 for page in json.load(gzip.open(p)).get('payload',{}).get('query',{}).get('pages',[]):
  wiki['pages']+=1
  for revision in page.get('revisions',[]):
   s=revision.get('slots',{}).get('main',{}).get('content','')
   for y in [1979,1989]:
    if str(y) not in s:continue
    wiki[f'{y}_literal_year_pages']+=1
    for m in re.finditer(r'\|\s*'+str(y)+r'\s*=\s*([\d][\d \u00a0]*)(?=\s*(?:\||\n|}|<))',s):
     qty=int(re.sub(r'\s','',m[1]));key=(page['title'],qty)
     if key not in oldkeys[y]:miss.append(dict(year=y,article_title=page['title'],population=qty,source_file=str(p),source_sha256=pins[str(p)],source_locator=f"pageid={page['pageid']};revid={revision['revid']};character={m.start()}",context=s[max(0,m.start()-150):m.end()+150],admission_status='candidate_only'))
pd.DataFrame(miss,columns=['year','article_title','population','source_file','source_sha256','source_locator','context','admission_status']).to_parquet(O/'wikipedia_template_parser_gaps.parquet',index=False)
summary['wikipedia_full_raw_inventory']=dict(wiki);summary['wikipedia_existing_template_parser_missing_hits']=len(miss)
(H/'receipt.json').write_text(json.dumps({'summary':summary,'inputs':pins,'outputs':{p.name:{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in O.glob('*.parquet')}},ensure_ascii=False,indent=2));(O/'receipt.json').write_text((H/'receipt.json').read_text());print(json.dumps(summary,ensure_ascii=False,indent=2))
