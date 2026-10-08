import json,gzip,collections,zipfile,re,hashlib
from pathlib import Path
import pandas as pd
O=Path(__file__).parent;B=O.parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();a=pd.read_csv(O/'own_current_point_source_witnesses.csv.gz',keep_default_na=False);need=collections.defaultdict(dict);gn={}
for z in a.to_dict('records'):
 q=json.loads(z['own_current_wiki_claims_json'])
 if q:
  prop=json.loads(z['broader_Wiki_physical_binding_context_json'])['binding_property']
  for p,k in [('P625','coord'),('P31','p31'),(prop,'codes'),('P721','p721extra')]:
   for v in q[k]:need[v['source_file']][int(v['line_number'])]=(z['own_current_entity'],p,str(v['value_raw']))
 g=json.loads(z['broader_GeoNames_ownpoint_source_witness_json'])
 if g:gn[g['geonames_row'][0]]=g
count=0;pins={}
for fn,lines in need.items():
 p=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/fn;pins[str(p)]=sha(p);seen=set()
 with gzip.open(p,'rt') as f:
  for ln,line in enumerate(f,1):
   if ln in lines:
    qid,prop,value=lines[ln];v=json.loads(line);assert v['item'].rsplit('/',1)[-1]==qid and v['property'].rsplit('/',1)[-1]==prop and str(v['value'])==value,(fn,ln);seen.add(ln);count+=1
   if ln>=max(lines):break
 assert seen==set(lines)
G=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');pins[str(G)]=sha(G);seen=set();adm={}
with zipfile.ZipFile(G) as zf:
 with zf.open('RU.txt') as f:
  for b in f:
   v=b.decode('utf8').rstrip('\n').split('\t')
   if len(v)<19:continue
   if v[6:8]==['A','ADM1']:adm[v[10]]=v
   if v[0] in gn:assert v==gn[v[0]]['geonames_row'];assert v[6]=='P' and v[7] in ['PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLC'] and v[8]=='RU';seen.add(v[0])
assert seen==set(gn)
for v in gn.values():assert adm[v['geonames_row'][10]]==v['geonames_ADM1']
C=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');cl=pd.read_parquet(C).set_index('historical_okato');SQL=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql');lines=SQL.read_text().splitlines();DBF=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf');PAR=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet');geo=pd.read_parquet(PAR).set_index('record_number_1based');active=json.load(gzip.open(B/'frozen_active_point_uses.json.gz','rt'));literal=[]
with DBF.open('rb') as stream:
 for z in a.to_dict('records'):
  sid=z['target_source_record_id'];p=active[sid];rec=re.search(r'(?:raw_dbf_record_number_1based|DBF_record_1based|DBFrecord)\s*=\s*(\d+)',str(p['point_origin_locator']));assert rec,sid;g=geo.loc[int(rec[1])];stream.seek(int(g.record_byte_offset_0based));payload=stream.read(395);text=payload.decode('cp1251');assert payload[:1]==b' ' and g.name_raw.strip() in text;assert (float(g.latitude_from_lat),float(g.longitude_from_long))==(float(p['latitude']),float(p['longitude']));c=cl.loc[str(z['old_raw_classifier_code'])];assert c.is_settlement_raw=='t';line=lines[int(c.source_line_1based)-1];assert str(z['old_raw_classifier_code']) in line and c['name'] in line;literal.append({'target_source_record_id':sid,'Geo_record_1based':int(rec[1]),'Geo_raw_code':g.historical_okato,'Geo_literal_name':g.name_raw,'classifier_physical_NP_code':z['old_raw_classifier_code'],'classifier_source_line_1based':int(c.source_line_1based),'classifier_literal_line':line,'Geo11_to_NP8_bridge':str(g.historical_okato)==str(z['old_raw_classifier_code'])+'000'})
for p in [C,SQL,DBF,PAR]:pins[str(p)]=sha(p)
pd.DataFrame(literal).to_csv(O/'literal_old_raw_Geo_and_physical_classifier_checks.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'status':'Every admitted raw Wiki value, GN point and ADM1 row, old raw DBF point record and own physical NP classifier literal checked independently','raw_Wiki_claim_values_checked':count,'raw_GeoNames_entities_checked':len(gn),'raw_old_Geo_and_classifier_targets_checked':len(literal),'input_pins':pins};(O/'literal_source_verification_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print({k:v for k,v in r.items() if k!='input_pins'})
