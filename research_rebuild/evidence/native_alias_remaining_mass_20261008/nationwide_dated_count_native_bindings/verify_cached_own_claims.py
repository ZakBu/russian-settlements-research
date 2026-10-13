import json,gzip,re,sys
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
O=Path(__file__).parent;d=pd.read_csv(O/'actual30_remaining_native02_current_candidates.csv.gz',dtype=str,keep_default_na=False);rows=[];holds=[];pins={}
def val(x):return x.get('mainsnak',{}).get('datavalue',{}).get('value')
def code(x):
 s=str(x).removesuffix('.0');return s if s.isdigit() else ''
def eqcode(a,b):
 a,b=code(a),code(b);return bool(a and b and (a==b or (len(a) in [10,11] and len(b) in [10,11] and a.zfill(11)==b.zfill(11))))
tsvpath=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');pins[str(tsvpath)]=sha(tsvpath);wanted=set(d.qid);native_tsv={}
for i,line in enumerate(tsvpath.open(),1):
 parts=line.rstrip().split('\t');qs=re.findall(r'Q\d+',parts[0]);q=qs[0] if qs else ''
 if q in wanted:native_tsv.setdefault(q,[]).append({'line_1based':i,'literal':line.rstrip(),'code_fields':parts[1:3]})
for path,g in d.groupby('claim_source_file'):
 p=Path(path)
 if not p.exists() or not path.endswith(('.json','.json.gz')):
  for z in g.to_dict('records'):holds.append({'old_source_record_id':z['old_source_record_id'],'reason':'No raw own entity archive in existing datedclaimbinding','path':path})
  continue
 j=json.load(gzip.open(p,'rt') if path.endswith('.gz') else p.open());entities=j.get('entities',j.get('payload',{}).get('entities',{}));pins[path]=sha(p)
 for z in g.to_dict('records'):
  q=z['qid'];e=entities.get(q,{})
  if not e:holds.append({'old_source_record_id':z['old_source_record_id'],'qid':q,'reason':'OwnQID absent from cached archive'});continue
  claims=e.get('claims',{});label=e.get('labels',{}).get('ru',{}).get('value','');desc=e.get('descriptions',{}).get('ru',{}).get('value','');aliases=[x['value'] for x in e.get('aliases',{}).get('ru',[])];names=[label]+aliases
  nativekeys={normalize(z['current_name']),normalize(z['old_name'])};namepositive=any(normalize(v) in nativekeys for v in names);codes=[val(c) for c in claims.get('P764',[])];positive=[x for x in codes if eqcode(x,z['current_oktmo'])];tsvpositive=[x for x in native_tsv.get(q,[]) if any(eqcode(v.strip('\"'),z['current_oktmo']) or eqcode(v.strip('\"'),z['current_okato']) for v in x['code_fields']) and normalize(z['current_name']) in normalize(x['literal'])];p625=[val(c) for c in claims.get('P625',[]) if isinstance(val(c),dict)];pop=[]
  for c in claims.get('P1082',[]):
   v=val(c)
   if not isinstance(v,dict) or 'amount' not in v:continue
   try:amount=float(v['amount'])
   except ValueError:continue
   dates=[x.get('datavalue',{}).get('value',{}) for x in c.get('qualifiers',{}).get('P585',[])];date=[x for x in dates if str(x.get('time','')).startswith('+2002-') and int(x.get('precision',0))>=9]
   if amount==float(z['native2002_population']) and date:pop.append({'statement_id':c.get('id'),'amount':v['amount'],'dates':date,'references':c.get('references',[])})
  cp=json.loads(z['current_admitted_point']);carrier=q in str(cp.get('coordinate_source_record_id',''))+' '+str(cp.get('point_origin_locator',''));distance=min([distance_km((cp['latitude'],cp['longitude']),(x['latitude'],x['longitude'])) for x in p625],default=None) if cp else None
  status='candidate_positive_raw_claim_own_code_name' if pop and (positive or tsvpositive) and namepositive and cp else 'hold_raw_date_or_current_own_code_name_or_point'
  row=dict(z,raw_own_label=label,raw_own_description=desc,raw_aliases=json.dumps(aliases,ensure_ascii=False),raw_P764_codes=json.dumps(codes,ensure_ascii=False),exact_native_current_P764=bool(positive),positive_alternative_native_TSV_code=bool(tsvpositive),positive_native_TSV_source_rows=json.dumps(tsvpositive,ensure_ascii=False),native_current_code_binding_rule='Exact native11-digit code, restoring only numeric publisher leadingzero' if positive else 'Independent cached TSV own-QID native OKATO/OKTMO/name code binding',raw_positive_native_P764=json.dumps(positive),raw_2002_count_date_claims=json.dumps(pop,ensure_ascii=False),raw_P625_points=json.dumps(p625,ensure_ascii=False),admitted_current_point_QID_binding=carrier,min_raw_P625_to_admitted_current_point_km=distance,own_name_or_alias_positive=namepositive,raw_entity_source_sha256=pins[path],raw_status=status);rows.append(row)
pd.DataFrame(rows).to_csv(O/'raw_cached_own_claim_binding_checks.csv.gz',index=False,compression='gzip');pd.DataFrame(holds).to_csv(O/'raw_cached_claim_archive_holds.csv',index=False);(O/'cached_entity_source_pins.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2));f=pd.DataFrame(rows);good=f[f.raw_status.eq('candidate_positive_raw_claim_own_code_name')];r={'raw_own_item_checks':len(f),'positive_date_count_native_current_code_name_point':len(good),'immediate_full3_candidates':int(good.status.eq('immediate_full3_candidate').sum()),'immediate_old2002_population':int(pd.to_numeric(good[good.status.eq('immediate_full3_candidate')].native2002_population).sum()),'all_old2002_population':int(pd.to_numeric(good.native2002_population).sum()),'archive_holds':len(holds)};(O/'raw_own_claim_positive_counts.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False));print(good.assign(p=pd.to_numeric(good.native2002_population)).sort_values('p',ascending=False)[['old_name','region','native2002_population','current_county','status']].head(25).to_string(index=False))
