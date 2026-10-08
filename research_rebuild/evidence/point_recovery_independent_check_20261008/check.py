import csv,gzip,json,hashlib,re
from pathlib import Path
import pandas as pd
base=Path('/workspace/russian-settlements-research/research_rebuild/evidence');src=base/'baseline_seven_ownpoint_recovery_20261008';out=base/'point_recovery_independent_check_20261008'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
pins={str(p):sha(p) for p in src.iterdir() if p.is_file()}
w=json.loads((src/'native_point_witnesses.json').read_text()); comps=json.loads((src/'active_seven_components.json').read_text())
with gzip.open(src/'accepted_point_use_delta.csv.gz','rt') as f: delta=list(csv.DictReader(f))
tsv=Path(delta[0]['point_origin_file']);sql=Path(delta[0]['classifier_origin_file']);rawfile=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
raw=pd.read_parquet(rawfile)
lines={r['literal_TSV_line_1based'] for r in w}; sqlnums={r['classifier_source_line_1based'] for r in w};found={};sf={}
with tsv.open() as f:
 header=next(csv.reader([next(f)],delimiter='\t'))
 for n,line in enumerate(f,2):
  if n in lines:found[n]=dict(zip(header,next(csv.reader([line],delimiter='\t'))))
with sql.open() as f:
 for n,line in enumerate(f,1):
  if n in sqlnums:sf[n]=line.rstrip('\n')
qids={r['wikidata_qid'].split('/')[-1].rstrip('>') for r in w};claims={q:[] for q in qids};truthypins={}
for path in sorted(Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims').glob('*.jsonl.gz')):
 used=False
 try:
  with gzip.open(path,'rt') as f:
   for n,line in enumerate(f,1):
    r=json.loads(line);q=r.get('item','').rsplit('/',1)[-1]
    if q in qids and r.get('property','').rsplit('/',1)[-1] in {'P764','P31','P625'}:
     claims[q].append(dict(file=str(path),line=n,property=r['property'].rsplit('/',1)[-1],value=r['value']));used=True
 except (OSError,ValueError):pass
 if used:truthypins[str(path)]=sha(path)
rows=[];literal=[]
for carrier in sorted({r['point_source_record_id'] for r in delta}):
 ws=[r for r in w if r['carrier_source_record_id']==carrier];ds=[r for r in delta if r['point_source_record_id']==carrier];c=next(c for c in comps if c['carrier']==carrier);obs={r['source_record_id']:r for r in c['observations']};r=ws[0];q=r['wikidata_qid'].split('/')[-1].rstrip('>');native=raw.iloc[int(carrier.rsplit(':',1)[-1])-1]
 assert len(ds)==3 and {d['target_source_record_id'] for d in ds}==set(obs)
 for item in ws:assert found[item['literal_TSV_line_1based']]==item['literal_TSV_row'];assert sf[item['classifier_source_line_1based']]==item['classifier_raw_line']
 coord=re.fullmatch(r'POINT\(([-\d.]+) ([-\d.]+)\)',r['literal_TSV_row']['?coord']);lon,lat=map(float,coord.groups()); assert all(float(d['latitude'])==lat and float(d['longitude'])==lon for d in ds)
 assert all(d['population_or_quality_modified']=='False' and d['identity_changes']=='False' and 'retrospective continuity inference' in d['coordinate_time_interpretation'] for d in ds)
 owncodes=[x['value'] for x in claims[q] if x['property']=='P764'];types=[x['value'].rsplit('/',1)[-1] for x in claims[q] if x['property']=='P31'];coords=[x['value'] for x in claims[q] if x['property']=='P625']
 rows.append(dict(carrier_source_id=carrier,name=obs[carrier]['settlement_name'],own_OKTMO=r['native_own_OKTMO'],own_OKATO=r['own_OKATO'],qid=q,latitude=lat,longitude=lon,TSV_lines=','.join(str(v['literal_TSV_line_1based']) for v in ws),classifier_line=r['classifier_source_line_1based'],classifier_label=r['classifier_literal_name'],native_raw_row_json=json.dumps(native.to_dict(),ensure_ascii=False,default=str),truthy_P764=';'.join(owncodes),truthy_P31=';'.join(types),truthy_P625=';'.join(coords),truthy_claims_present=bool(claims[q]),own_P764_confirmed=r['native_own_OKTMO'] in owncodes,own_P625_confirmed=r['literal_TSV_row']['?coord'] in coords,old_provider_code=r['original_provider_code'],old_provider_other_NP=r['other_published_NP'],target_count=len(ds),status='pending_native_type_review'))
 literal.append(dict(carrier=carrier,TSV=ws,truthy=claims[q],unchanged_source_observations=c['observations']))
print(json.dumps([{k:v for k,v in r.items() if k!='native_raw_row_json'} for r in rows],ensure_ascii=False,indent=2))
(out/'literal_reopened_witnesses.json').write_text(json.dumps(literal,ensure_ascii=False,indent=2))
with (out/'six_carrier_checks.csv').open('w') as f:wr=csv.DictWriter(f,fieldnames=rows[0]);wr.writeheader();wr.writerows(rows)
pins.update({str(p):sha(p) for p in [tsv,sql,rawfile]});pins.update(truthypins);(out/'input_pins.json').write_text(json.dumps(pins,indent=2))
