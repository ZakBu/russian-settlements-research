import json,csv,gzip,zipfile,re,hashlib
from pathlib import Path
import pandas as pd,xlrd
p=Path(__file__).parent;s=p.parent/'inherited_extreme_Geo_ownpoint_correction_20261008';selected=json.loads((p/'selected_source_witnesses.json').read_text())
def sha(f):return hashlib.sha256(Path(f).read_bytes()).hexdigest()
def norm(t):return re.sub(r'\s+',' ',str(t).lower().replace('ё','е')).strip()
def name(t):
 t=norm(t)
 return re.sub(r'^(?:населенный пункт|железнодорожная станция|поселок при станции|поселок станции|поселок городского типа|рабочий поселок|курортный поселок|сельский поселок|станица|деревня|поселок|хутор|село|город|аул|улус|заимка|пгт|станция)\s+','',t)
zipfilep=Path(selected[0]['anchor_proof']['anchor_origin_file']);rawp=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');raw=pd.read_parquet(rawp,columns=['object_level','object_name','oktmo','region','mun_upper','mun_lower','population']);raw['raw_row_1based']=range(1,len(raw)+1);raw['np_name']=raw.object_name.map(name)
needed={int(r['anchor_proof']['anchor_origin_locator'].split('line ')[1].split(';')[0]) for r in selected};GN={};ADM={};gname=[]
with zipfile.ZipFile(zipfilep) as z:
 with z.open('RU.txt') as f:
  for n,b in enumerate(f,1):
   vals=b.decode().rstrip('\n\r').split('\t')
   if n in needed:GN[n]=vals
   if vals[6:9]==['A','ADM1','RU']:ADM[vals[10]]=dict(line=n,row=vals)
   for r in selected:
    if vals[6]=='P' and vals[8]=='RU' and vals[10]==r['anchor_proof']['literal_GeoNames_point_fields'][10] and norm(r['name']) in {norm(a) for a in vals[3].split(',')}:
     gname.append(dict(carrier=r['carrier_source_record_id'],line=n,row=vals))
pins={str(f):sha(f) for f in s.iterdir() if f.is_file()};pins.update({str(rawp):sha(rawp),str(zipfilep):sha(zipfilep)});ledger=[];witness=[]
for r in selected:
 sid=r['carrier_source_record_id'];a=r['anchor_proof'];line=int(a['anchor_origin_locator'].split('line ')[1].split(';')[0]);gn=GN[line];assert gn==a['literal_GeoNames_point_fields'];assert gn[6:9]==['P','PPL','RU'];assert float(gn[4])==r['anchor_latitude'] and float(gn[5])==r['anchor_longitude'];assert norm(r['name']) in {norm(v) for v in gn[3].split(',')}
 current=raw.iloc[int(sid.rsplit(':',1)[-1])-1];adm=ADM[gn[10]];assert adm['row']==a['literal_GeoNames_ADM1_fields']; assert norm(current['region']) in {norm(v) for v in adm['row'][3].split(',')}
 rivals=raw[(raw.object_level=='Населенный пункт')&(raw.region==current['region'])&(raw.np_name==norm(r['name']))];assert len(rivals)==1 and int(rivals.iloc[0].raw_row_1based)==int(sid.rsplit(':',1)[-1]);gr=[x for x in gname if x['carrier']==sid];print('GNNAME',r['name'],[(g['row'][0],g['row'][7],g['row'][4:6]) for g in gr])
 hist=[]
 for o in r['old_native_and_classifier_proofs']:
  f=Path(o['native_file']);pins[str(f)]=sha(f);assert pins[str(f)]==o['native_sha256'];book=xlrd.open_workbook(f);sheet=book.sheet_by_name(o['native_sheet']);n=o['native_row_1based'];literal=sheet.row_values(n-1);assert literal==o['native_literal_row'];assert any(norm(r['name']) in norm(x) for x in literal)
  # Capture literal nearby county-level published hierarchy, independent of acceptance predicate.
  headings=[]
  for j in range(n-2,-1,-1):
   vals=sheet.row_values(j);text=' | '.join(str(v) for v in vals if isinstance(v,str) and v.strip())
   if re.search(r'район|городской округ',text,re.I):
    headings.append(dict(row_1based=j+1,text=text))
    if len(headings)==3:break
  hist.append(dict(source_id=o['target_source_record_id'],literal_row=literal,published_county_context=headings,classifier_name=o['classifier_literal_name'],classifier_type=o['classifier_literal_status'],accepted_component_identity_preserved=o['accepted_component_identity_preserved']))
 ledger.append(dict(carrier=sid,name=r['name'],status='PASS',GN_id=gn[0],GN_line=line,GN_ADM1=gn[10],native_region=current['region'],native_county=current['mun_upper'],native_population=str(current['population']),native_rivals_alltyped_fullraw_blankpop_included=len(rivals),GN_sameCyrillic_region_physical_rivals=len(gr),official_modern_code_asserted=False,admin2='UNKNOWN',historical_point_interpretation='accepted identity continuity; no census-day measurement',historical_sources_reopened=len(hist)))
 witness.append(dict(carrier=sid,GN_literal=gn,ADM1_literal=adm,all_GN_same_Cyrillic_ADM1_records=gr,all_original2021_rivals=rivals.to_dict('records'),historical_literal_sources=hist))
with (p/'four_anchor_ledger.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=ledger[0]);w.writeheader();w.writerows(ledger)
(p/'literal_witnesses.json').write_text(json.dumps(witness,ensure_ascii=False,indent=2,default=str));(p/'input_pins.json').write_text(json.dumps(pins,indent=2));print(json.dumps(ledger,ensure_ascii=False))
