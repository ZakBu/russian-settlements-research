import csv,json,re,collections,hashlib
from pathlib import Path
import pyarrow.parquet as pq
E=Path(__file__).resolve().parent;P=E.parent
old={x['source_record_id']for x in csv.DictReader(open(P/'rsfsr1989_external_points_20261013/external_point_delta.csv'))};rows=[x for x in csv.DictReader(open(P/'rsfsr1989_primary_binding_20261013/primary_bindings.csv'))if not x['binding_status'].startswith('bound')and x['source_record_id']not in old];rows.sort(key=lambda x:-int(x['population_total']));(E/'target_rows.json').write_text(json.dumps(rows[:35],ensure_ascii=False,indent=2));alias={'Шпаковское':'Михайловск','Каспийский':'Лагань','Лянторский':'Лянтор','Кодинский':'Кодинск','Петрокрепость':'Шлиссельбург','Теучежск':'Адыгейск','Красноармейская':'Полтавская','Чегем Первый':'Чегем'}
def norm(x):return' '.join(re.sub('[^а-я0-9]+',' ',x.lower().replace('ё','е')).split())
regs=collections.defaultdict(collections.Counter)
core=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
for b in pq.ParquetFile(core).iter_batches(columns=['region_norm','oktmo'],batch_size=8192):
 for x in b.to_pylist():
  if x['oktmo']and re.fullmatch('[0-9]{7,11}',x['oktmo']):regs[x['oktmo'].zfill(8)[:2]][x['region_norm']]+=1
prefix={k:v.most_common(1)[0][0]for k,v in regs.items()};index=collections.defaultdict(list)
f=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv')
for x in csv.DictReader(open(f),delimiter='\t'):
 label=re.sub(r'^"|"@ru$','',x['?label']);coord=x['?coord'];code=x['?oktmo'].strip('"');q=re.search(r'Q\d+',x['?item'])
 if not q or not coord.startswith('POINT('):continue
 rg=prefix.get(code.zfill(8)[:2]);index[(rg,norm(label))].append(dict(qid=q[0],label=label,coord=coord,oktmo_raw=code,admin_raw=x['?adminLabel'],article=x['?article']))
out=[]
for x in rows:
 n=x['source_name_parsed_for_binding'];wanted=alias.get(n,n);cand=[]
 for rg in x['current_region_alias'].split('|'):cand+=index.get((rg,norm(wanted)),[])
 unique={z['qid']:z for z in cand}
 if unique:out.append(dict(source_record_id=x['source_record_id'],historical_name=n,current_query_name=wanted,region=x['qualified_historical_region'],population_total=int(x['population_total']),candidate_qids=list(unique.values())))
(E/'cached_candidates.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));(E/'cache_receipt.json').write_text(json.dumps(dict(cache_path=str(f),cache_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),candidate_source_rows=len(out),region_namespace_prefix_map=prefix),ensure_ascii=False,indent=2));print(json.dumps(out[:25],ensure_ascii=False,indent=2))
