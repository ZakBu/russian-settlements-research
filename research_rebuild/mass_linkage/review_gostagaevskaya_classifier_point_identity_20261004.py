#!/usr/bin/env python3
"""Independent finite review of the Gostagaevskaya shared-point recovery.

Replays the cited publisher rows, native historical classifier rows, and the
GeoNames raw physical-place line. Emits candidate-only edges/point uses; it
does not modify the accepted graph, point ledger, or populations.
"""
from __future__ import annotations
import csv,hashlib,json,math,struct,subprocess,zipfile
from pathlib import Path
import xlrd,pyarrow.parquet as pq

PACKET=Path('/workspace/settlements-work/continuation_20261004/root/large_np_shared_point_recovery_gost_sup_20261004')
OUT=Path('/workspace/settlements-work/continuation_20261004/independent_review/gostagaevskaya_classifier_point_review_v2')
FROZEN=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
GRAPH=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_tenth_reviewed1117/accepted_identity_edges.parquet')
POINTS=Path('/workspace/settlements-work/continuation_20261004/accepted_mass_tenth_reviewed1117/accepted_point_uses.parquet')
RAW2021=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
XLS2002=Path('/workspace/settlements-raw/data/raw/2002/036_81b258bc42_02c_Krasnodarski-krai.xls')
PDF2010=Path('/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf')
SQL2009=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql')
DBF2011=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
GNZIP=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
RCSIP=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/rcsi_github_settlements.csv')
SUPSEKH_PACKET=Path('/workspace/settlements-work/continuation_20261004/root/supsekh_point_choice_supplement_20261004')
EXPECTED={
 'producer_receipt':'376b8fffa0276e822a767accd2b56be556f21755f084bd7f3170b3f411e015ff',
 'candidate_points':'7d7ed4f84f3329fcdb2d4ec44368634c0a504fe119831395ed6b43ba6fa91924',
 'publisher_context':'f3294857cc2684eadae3f359fd9dcc198dfd2d8a23fffea31c020709f43edc41',
 'identity_context':'e6601d673d86a1698615edcc234a48c40e71f7264dce008110b3c0a7b65617bf',
 'feature_review':'3ee11beb877e48b1e818ba09df5253670153d6d847fb0da74ef2294f5f46c813',
 'qid_check':'ec4df6241df83230c3cf3c56ada21f824314b47ee904c67c9940d1dd44f81fd0',
 'graph':'19861c11048f191a540aba453f11194a540934fbe350f553e37a42908393d013',
 'selected':'4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
 'source_evidence':'e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327',
 'raw2021':'86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14',
 'xls2002':'9588f5aa5f8de40a290739a880e624a6d34ea566377b9a7f4df1674f1cf99121',
 'pdf2010':'42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3',
 'sql2009':'6062e097ad504ba8b4bc130599ca4825c54f2b98486d16aed15ac143fcd705db',
 'dbf2011':'d1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650',
 'gnzip':'9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4',
 'latest_points':'870ccd0af86889e5c8e2c01bddd1d3c53401ccba216d7ce77624e5f848f724cc',
 'supsekh_supplement_receipt':'04509555d0069c648656aa4ff9fabd910b542cc970bcc27e3285dac507c55ab4',
 'supsekh_supplement_evidence':'ff1d9fea8fba859b2a2494c9bc8827e0dd56e72127d77dcd006f9a510b02f198',
 'rcsi':'50317de1174e35fca893f5c8d965d9c7f40d6a60a06149b96672bb1a134268d0',
}
IDS={
 'GOST':{
  2002:'2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:359',
  2010:'ROSSTAT2010:T5:p76:l44',
  2021:'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46763'},
 'SUPS':{
  2002:'2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:392',
  2010:'ROSSTAT2010:T5:p76:l47',
  2021:'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46789'},
}
SPECS={
 'graph':GRAPH,'selected':FROZEN/'selected_observations.parquet','source_evidence':FROZEN/'source_evidence.parquet',
 'raw2021':RAW2021,'xls2002':XLS2002,'pdf2010':PDF2010,'sql2009':SQL2009,'dbf2011':DBF2011,'gnzip':GNZIP,'latest_points':POINTS,
 'producer_receipt':PACKET/'receipt.json','candidate_points':PACKET/'candidate_point_uses.csv','publisher_context':PACKET/'all_year_publisher_context.csv',
 'identity_context':PACKET/'identity_and_native_code_context.csv','feature_review':PACKET/'geonames_same_name_feature_review.csv','qid_check':PACKET/'current_cached_qid_p625_check.csv',
 'supsekh_supplement_receipt':SUPSEKH_PACKET/'receipt.json','supsekh_supplement_evidence':SUPSEKH_PACKET/'supsekh_point_choice_evidence.csv','rcsi':RCSIP}

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def readcsv(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def hav(a,b,c,d):
 r=math.pi/180;p1=a*r;p2=c*r;dp=(c-a)*r;dl=(d-b)*r
 return 6371.0088*2*math.asin(math.sqrt(math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2))
def dbf_record(path,row1):
 b=path.read_bytes();nrec=struct.unpack('<I',b[4:8])[0];hlen=struct.unpack('<H',b[8:10])[0];rlen=struct.unpack('<H',b[10:12])[0]
 fields=[];pos=32
 while b[pos]!=0x0d:
  name=b[pos:pos+11].split(b'\0')[0].decode('ascii');length=b[pos+16];fields.append((name,length));pos+=32
 if row1<1 or row1>nrec:raise ValueError('DBF record out of range')
 raw=b[hlen+(row1-1)*rlen:hlen+row1*rlen];off=1;out={}
 for name,length in fields:out[name]=raw[off:off+length].decode('cp1251').strip();off+=length
 return out,hashlib.sha256(raw).hexdigest(),raw
def parquet_record(path,row1,cols):
 pf=pq.ParquetFile(path);base=0
 for i in range(pf.metadata.num_row_groups):
  n=pf.metadata.row_group(i).num_rows
  if base<row1<=base+n:return pf.read_row_group(i,columns=cols).slice(row1-base-1,1).to_pylist()[0]
  base+=n
 raise ValueError('Parquet row not found')
def main():
 if OUT.exists():raise FileExistsError(f'immutable independent review exists: {OUT}')
 input_pins={}
 for label,p in SPECS.items():
  got=sha(p);expected=EXPECTED[label]
  if got!=expected:raise ValueError(f'{label} input hash mismatch {got}')
  input_pins[label]={'path':str(p),'sha256':got,'bytes':p.stat().st_size}
 # Pin the original producer receipt to exact row-bearing artifacts.
 parent=json.loads(SPECS['producer_receipt'].read_text())
 if parent.get('status')!='candidate_only_no_application' or parent['outputs']['candidate_point_uses.csv']['sha256']!=EXPECTED['candidate_points']:raise ValueError('producer candidate packet pin/status mismatch')
 sup_receipt=json.loads(SPECS['supsekh_supplement_receipt'].read_text())
 if sup_receipt.get('status')!='bounded_point_choice_supplement_candidate_only' or sup_receipt.get('outputs',{}).get('supsekh_point_choice_evidence.csv',{}).get('sha256')!=EXPECTED['supsekh_supplement_evidence']:raise ValueError('Supsekh supplement receipt/evidence mismatch')
 context=readcsv(SPECS['publisher_context']); bynameyear={(r['target_name'],int(r['year'])):r for r in context}
 cpoints=readcsv(SPECS['candidate_points']); pointrows={r['point_candidate_id']:r for r in cpoints}
 idctx=readcsv(SPECS['identity_context']);feat=readcsv(SPECS['feature_review']);qid=readcsv(SPECS['qid_check'])
 # Exact raw publisher observations: 2002 spreadsheet plus its printed district hierarchy,
 # 2010 primary Table 5 page/row, and current raw Tochno row.
 wb=xlrd.open_workbook(str(XLS2002),on_demand=True);sh=wb.sheet_by_name('11')
 x2002={}
 for key,row in [('GOST',359),('SUPS',392)]:
  vals=sh.row_values(row-1)
  if int(vals[0])!=row:raise ValueError('2002 XLS row locator mismatch')
  x2002[key]={'source_row':row,'source_name_raw':str(vals[1]).strip(),'population':float(vals[2]),'parent_context_raw':str(sh.cell_value(row-2,1)).strip()}
 pdftext=subprocess.run(['pdftotext','-f','76','-l','76','-layout',str(PDF2010),'-'],check=True,capture_output=True,text=True).stdout
 page_lines=pdftext.splitlines()
 pdf_rows={}
 for key,phrase,pop in [('GOST','станица Гостагаевская',9772),('SUPS','село Супсех',6669)]:
  exact=[ln.strip() for ln in page_lines if phrase in ln]
  if len(exact)!=1 or str(pop) not in exact[0]:raise ValueError(f'2010 raw primary table row mismatch {key}')
  if 'Анапский район - сельское население' not in pdftext:raise ValueError('2010 district hierarchy heading absent')
  pdf_rows[key]={'pdf_page_1based':76,'printed_page':75,'raw_label':exact[0],'district_heading':'Анапский район - сельское население'}
 # Re-read the cited classifier rows.
 sql_lines=SQL2009.read_bytes().splitlines(keepends=True)
 sqlrows={}
 for key,n,code,name,stype in [('GOST',3401,'03203807001','ст-ца Гостагаевская','станица'),('SUPS',3438,'03203819001','с Супсех','село')]:
  rawline=sql_lines[n-1];cols=rawline.decode('utf-8').rstrip('\r\n').split('\t')
  if cols[0]!=code or cols[1]!=name or cols[3]!=stype:raise ValueError(f'2009 SQL classifier row mismatch {key}')
  sqlrows[key]={'line_1based':n,'raw_line':rawline.decode('utf-8').rstrip('\r\n'),'line_sha256':hashlib.sha256(rawline).hexdigest(),'okato':cols[0],'raw_name':cols[1],'parsed_name':cols[2],'raw_type':cols[3]}
 dbfrows={}
 for key,n,code,name,stype,lat,lon in [('GOST',1663,'03203807001','ст-ца Гостагаевская','1',45.022720,37.498653),('SUPS',1692,'03203819001','с Супсех','1',44.859840,37.367494)]:
  rec,rsha,raw=dbf_record(DBF2011,n);literal=rec['TER']+rec['KOD1']+rec['KOD2']+rec['KOD3']
  if literal!=code or rec['NAME1']!=name or rec['TYPE_NP']!=stype or float(rec['LAT'])!=lat or float(rec['LONG'])!=lon:raise ValueError(f'2011 DBF classifier row mismatch {key}')
  dbfrows[key]={'record_1based':n,'row_sha256':rsha,'raw_name':rec['NAME1'],'raw_type_code':rec['TYPE_NP'],'okato_literal':literal,'latitude':lat,'longitude':lon,'raw_name_type_source_namespace':'GeoKLADR DBF locality row; not a current OKTMO claim'}
 # Re-read exact GeoNames raw rows and coordinate corroboration.
 gn_by_id={}; needed_gn={98324:'GOST',25650:'SUPS',153094:'SUPS_ALT_PPL',151917:'SUPS_PPLX'}
 with zipfile.ZipFile(GNZIP) as z:
  with z.open('RU.txt') as f:
   pos=0
   for n in range(1,max(needed_gn)+1):
    raw=f.readline();end=pos+len(raw)
    if n in needed_gn:
     cols=raw.decode('utf-8').rstrip('\r\n').split('\t')
     gh=hashlib.sha256(raw).hexdigest()
     label=needed_gn[n]
     if label=='GOST': expected=('559252','P','PPL','Гостагаевская','e6eaab4cdb7b6c224f2ca9f64ff33958f8376a228bed074c317da9e39e8e2cbb',14488358,14488571)
     elif label=='SUPS':expected=('486166','P','PPL','Супсех','7cce4f25a6ce19117ed24b340bc09bd857a46107a09d7d7e28283d8db5dd9678',3487900,3488012)
     elif label=='SUPS_ALT_PPL':expected=('867470','P','PPL','Супсех','cfff80db05525d5967de18f641057c839076a26da1d83225ffcb309cc520daea',22452675,22452784)
     else:expected=('866252','P','PPLX','Супсех','a566a5e1af986594d9a47a8a93cfd293e49aeb9fed61a1fd7cb9b8a1f3e9ccf0',22265530,22265641)
     alias='Гостагаевская' if label=='GOST' else 'Супсех'
     if cols[0]!=expected[0] or cols[6]!=expected[1] or cols[7]!=expected[2] or cols[8]!='RU' or alias not in cols[3].split(','):raise ValueError(f'GeoNames raw feature/alias mismatch: {label}')
     if alias not in cols[3].split(',') or pos!=expected[5] or end!=expected[6] or gh!=expected[4]:raise ValueError(f'GeoNames raw row locator/hash/alias mismatch: {label}')
     gn_by_id[label]={'geonameid':cols[0],'name':cols[1],'aliases':cols[3].split(','),'latitude':float(cols[4]),'longitude':float(cols[5]),'feature_class':cols[6],'feature_code':cols[7],'country':cols[8],'admin1':cols[10],'line':n,'byte_start':pos,'byte_end':end,'line_sha256':gh,'raw_line':raw.decode('utf-8').rstrip('\r\n')}
    pos=end
 # Independently replay the local secondary RCSI row for Supsekh. Its leading
 # zero OKTMO text is preserved as a separate provider literal, never equated.
 rcsi_line=None;rcsi_start=0
 with RCSIP.open('rb') as f:
  for line_no,line in enumerate(f,1):
   end=rcsi_start+len(line)
   if line_no==74819:
    rcsi_line=line;rcsi_end=end;break
   rcsi_start=end
 if rcsi_line is None or rcsi_start!=19661086 or rcsi_end!=19661339 or hashlib.sha256(rcsi_line).hexdigest()!='ddc393df579dc6dce10b5b50236d6470c620c4a5ded1fe635331208d3e200f79':raise ValueError('RCSI exact raw row location/hash mismatch')
 rcsi_fields=next(csv.reader([rcsi_line.decode('utf-8').rstrip('\r\n')],delimiter=';',quotechar='"'))
 if rcsi_fields[0]!='74817' or rcsi_fields[1]!='Краснодарский край' or rcsi_fields[2]!='Город-курорт Анапа' or rcsi_fields[3]!='Супсех' or rcsi_fields[4]!='с' or float(rcsi_fields[9])!=44.8588888888889 or float(rcsi_fields[10])!=37.3586111111111 or rcsi_fields[11]!='03703000311':raise ValueError('RCSI source field interpretation mismatch')
 rcsi={'file':str(RCSIP),'sha256':EXPECTED['rcsi'],'line_1based':74819,'byte_start_0based':rcsi_start,'byte_end_exclusive':rcsi_end,'line_sha256':hashlib.sha256(rcsi_line).hexdigest(),'raw_line':rcsi_line.decode('utf-8').rstrip('\r\n'),'raw_code_literal_preserved':rcsi_fields[11],'latitude':float(rcsi_fields[9]),'longitude':float(rcsi_fields[10]),'municipality':rcsi_fields[2],'settlement':rcsi_fields[3],'type':rcsi_fields[4]}
 # Verify selected/raw identity keys and source evidence for both possible targets.
 allids={IDS[n][y] for n in IDS for y in IDS[n]}
 selected=pq.read_table(FROZEN/'selected_observations.parquet',columns=['source_record_id','census_year','settlement_name','settlement_type','population','population_scope','is_additive_settlement_record','region_norm','region_raw','district_raw','municipality_raw','okato','oktmo','source_name_raw','source_file','source_sheet','source_row','source_locator'],filters=[('source_record_id','in',sorted(allids))]).to_pylist()
 sel={r['source_record_id']:r for r in selected}
 if set(sel)!=allids:raise ValueError('one or more six publisher rows absent from frozen selected observations')
 years_check=[]
 for name in ['GOST','SUPS']:
  for y,sid in IDS[name].items():
   r=sel[sid]
   if int(r['census_year'])!=y or r['settlement_name']!=('Гостагаевская' if name=='GOST' else 'Супсех'):raise ValueError('selected observation ID/name/year mismatch')
   years_check.append({'target':name,'year':y,'source_record_id':sid,'source_file':r['source_file'],'source_row':r['source_row'],'source_sheet':r['source_sheet'],'source_name_raw':r['source_name_raw'],'selected_name':r['settlement_name'],'selected_type':r['settlement_type'],'region_raw':r['region_raw'],'region_norm':r['region_norm'],'district_raw':r['district_raw'],'municipality_raw':r['municipality_raw'],'population_context_only':r['population'],'population_scope_raw':r['population_scope'],'is_additive':r['is_additive_settlement_record'],'okato_literal':r['okato'],'oktmo_literal':r['oktmo']})
 # Raw current provider rows match selected keys, but their shared coordinates are held out.
 rawcurrent={}
 for name in ['GOST','SUPS']:
  sid=IDS[name][2021];rowno=int(sid.rsplit(':parquet:',1)[1]);raw=parquet_record(RAW2021,rowno,['object_level','object_name','oktmo','region','settlement','population','latitude_dadata','longitude_dadata'])
  r=sel[sid]
  if raw['object_level']!='Населенный пункт' or raw['oktmo']!=r['oktmo'] or raw['object_name']!=r['source_name_raw'] or raw['region']!=r['region_raw'] or float(raw['population'])!=float(r['population']):raise ValueError(f'2021 raw publisher row replay mismatch {name}')
  rawcurrent[name]={'row_1based':rowno,**raw}
 if rawcurrent['GOST']['latitude_dadata']!=rawcurrent['SUPS']['latitude_dadata'] or rawcurrent['GOST']['longitude_dadata']!=rawcurrent['SUPS']['longitude_dadata']:raise ValueError('expected exact shared current wrong-point evidence changed')
 # Current native OKTMO uniqueness is rechecked in both selected rows and raw
 # Tochno. It disambiguates the publisher record only; no cross-namespace link.
 from collections import Counter
 sel_codes=Counter();sel_keys=Counter()
 for batch in pq.ParquetFile(FROZEN/'selected_observations.parquet').iter_batches(columns=['census_year','settlement_name','settlement_type','region_norm','oktmo'],batch_size=16384):
  for r in batch.to_pylist():
   if int(r['census_year'])==2021:
    sel_codes[str(r['oktmo'])]+=1;sel_keys[(str(r['settlement_name']),str(r['settlement_type']),str(r['region_norm']))]+=1
 raw_codes=Counter()
 for batch in pq.ParquetFile(RAW2021).iter_batches(columns=['oktmo'],batch_size=16384):raw_codes.update(str(v) for v in batch.column(0).to_pylist())
 oktmo_frequencies={}
 for name in ['GOST','SUPS']:
  current=sel[IDS[name][2021]];code=str(current['oktmo']);key=(str(current['settlement_name']),str(current['settlement_type']),str(current['region_norm']))
  oktmo_frequencies[name]={'raw_literal':code,'selected_2021_frequency':sel_codes[code],'raw_tochno_frequency':raw_codes[code],'selected_name_type_region_frequency':sel_keys[key]}
  if sel_codes[code]!=1 or raw_codes[code]!=1:raise ValueError(f'current native source code not unique: {name}')
 # Target point state on the actual current baseline.
 accepted_points=pq.read_table(POINTS,columns=['target_source_record_id','target_year','latitude','longitude','coordinate_source','point_origin_file','point_origin_locator','coordinate_admission_status'],filters=[('target_source_record_id','in',sorted(allids))]).to_pylist()
 accepted_point_map={(r['target_source_record_id'],int(float(r['target_year']))):r for r in accepted_points}
 for name in ['GOST','SUPS']:
  for year in [2002,2010]:
   old=accepted_point_map.get((IDS[name][year],year))
   if not old or old['coordinate_admission_status']!='reviewed_extension_rule_accepted' or old['coordinate_source']!='GeoKLADR 2011 source coordinate' or old['point_origin_file']!=str(DBF2011):
    raise ValueError(f'previously accepted historical point-use missing or changed: {name} {year}')
   if old['point_origin_locator']!=('raw_dbf_record_number_1based=1663;byte_offset_0based=657195' if name=='GOST' else 'raw_dbf_record_number_1based=1692;byte_offset_0based=668650'):
    raise ValueError(f'historical point-use origin locator changed: {name} {year}')
   if (float(old['latitude']),float(old['longitude']))!=( (45.02272,37.498653) if name=='GOST' else (44.85984,37.367494) ):
    raise ValueError(f'historical accepted classifier point changed: {name} {year}')
  if (IDS[name][2021],2021) in accepted_point_map:raise ValueError(f'current target already has an accepted point: {name}')
 relevant=[]
 for key in ['from_source_record_id','to_source_record_id']:
  for e in pq.read_table(GRAPH,columns=['from_source_record_id','to_source_record_id','relation','decision_status'],filters=[(key,'in',sorted(allids))]).to_pylist():
   if e not in relevant:relevant.append(e)
 if relevant:raise ValueError('historical/current target endpoints already participate in accepted edges; scope this review again')
 # Explain source-evidence quarantine and verify no disqualifying hard event flags.
 evtable=pq.read_table(FROZEN/'source_evidence.parquet',filters=[('source_record_id','in',sorted(allids))]).to_pylist(); evmap={}
 for outer in evtable:
  payload=json.loads(outer['source_evidence_json'])
  sid=outer['source_record_id'];year=int(outer['census_year'])
  if payload.get('source_record_id') not in (None,sid) or int(payload.get('census_year',year))!=year:raise ValueError('source evidence JSON identity/year mismatch')
  evmap[(sid,year)]=payload
 event_audit=[]
 for name in ['GOST','SUPS']:
  for y,sid in IDS[name].items():
   e=evmap.get((sid,y))
   if not e:raise ValueError('missing source evidence event row')
   if e.get('is_additive_settlement_record') is not True or e.get('is_federal_aggregate') is not False or e.get('legacy_same_year_collision') is not False or e.get('legacy_verified_successor_settlement_id') not in (None,'','null'):raise ValueError('physical hard event/grain flag blocks candidate')
   reasons=json.loads(e.get('legacy_identity_reasons') or '[]') if isinstance(e.get('legacy_identity_reasons'),str) else e.get('legacy_identity_reasons') or []
   if bool(e.get('legacy_identity_conflict')) and reasons!=['administrative_conflict']:raise ValueError('legacy conflict includes reason beyond the scoped admin-context mismatch')
   event_audit.append({'target':name,'year':y,'source_record_id':sid,'legacy_identity_conflict':e.get('legacy_identity_conflict'),'legacy_identity_reasons':reasons,'same_year_collision':e.get('legacy_same_year_collision'),'federal_aggregate':e.get('is_federal_aggregate'),'verified_successor':e.get('legacy_verified_successor_settlement_id'),'additive':e.get('is_additive_settlement_record'),'population_scope':e.get('population_scope')})
 # PPL source/point agreement and excluded feature distinction.
 dbf_distance=hav(gn_by_id['GOST']['latitude'],gn_by_id['GOST']['longitude'],dbfrows['GOST']['latitude'],dbfrows['GOST']['longitude'])
 if abs(dbf_distance-.507667)>0.00001:raise ValueError('source point-distance support changed')
 edge_rows=[];points=[];physical={}
 for target_name in ['GOST','SUPS']:
  srcids=IDS[target_name];target_name_ru='Гостагаевская' if target_name=='GOST' else 'Супсех';gnkey='GOST' if target_name=='GOST' else 'SUPS'
  type_expected='станица' if target_name=='GOST' else 'село'
  ctx=[r for r in years_check if r['target']==target_name]
  if any(r['selected_type']!=type_expected or r['region_norm']!='краснодарский' for r in ctx):raise ValueError(f'{target_name_ru} selected name/type/province context mismatch')
  if len({r['selected_name'] for r in ctx})!=1 or len({r['selected_type'] for r in ctx})!=1:raise ValueError(f'{target_name_ru} crossyear name/type changes')
  gn=gn_by_id[gnkey];dist=hav(gn['latitude'],gn['longitude'],dbfrows[target_name]['latitude'],dbfrows[target_name]['longitude'])
  physical[target_name]={'gn_to_2011_dbf_km':round(dist,6),'current_raw_to_gn_km':round(hav(rawcurrent[target_name]['latitude_dadata'],rawcurrent[target_name]['longitude_dadata'],gn['latitude'],gn['longitude']),6),'current_raw_to_2011_dbf_km':round(hav(rawcurrent[target_name]['latitude_dadata'],rawcurrent[target_name]['longitude_dadata'],dbfrows[target_name]['latitude'],dbfrows[target_name]['longitude']),6)}
  if dist>(.51 if target_name=='GOST' else .36):raise ValueError(f'{target_name_ru} named classifier point and selected PPL no longer form the reviewed local cluster')
  if target_name=='SUPS':
   d_rcsi=hav(gn['latitude'],gn['longitude'],rcsi['latitude'],rcsi['longitude'])
   if abs(d_rcsi-.748536)>0.00001 or abs(hav(gn_by_id['SUPS_ALT_PPL']['latitude'],gn_by_id['SUPS_ALT_PPL']['longitude'],dbfrows['SUPS']['latitude'],dbfrows['SUPS']['longitude'])-2.098626)>0.00001:
    raise ValueError('Supsekh selected/alternate feature spatial ranking changed')
  rule='exact 2002/2010/2021 publisher name, printed physical-settlement type and province agree; 2009 SQL and 2011 GeoKLADR repeat the same literal old OKATO locality row/code/type; independently named physical point sources corroborate locality. Administrative raw labels remain separate and boundary equivalence is not asserted; current OKTMO is used only to identify the exact 2021 publisher row.'
  for eid,y1,y2 in [(f'{target_name}-E-2002-2010',2002,2010),(f'{target_name}-E-2010-2021',2010,2021)]:
   a,b=srcids[y1],srcids[y2]
   edge_rows.append({'proposal_id':eid,'from_source_record_id':a,'to_source_record_id':b,'from_year':y1,'to_year':y2,'relation':'same_place','review_status':'independently_reviewed_candidate_for_root_application','rule':rule,'evidence_json':json.dumps({'selected_name_type_region_same':True,'source_rows_exactly_replayed':[a,b],'administrative_contexts_preserved_not_equated':True,'legacy_quarantine_resolution_scope':'exact administrative_conflict reason only; federal/successor/collision flags remain hard blocks','historical_OKATO_2009_literal':sqlrows[target_name]['okato'],'historical_OKATO_2011_literal':dbfrows[target_name]['okato_literal'],'current_OKTMO_used_only_as_exact_source_row_disambiguator':str(sel[srcids[2021]]['oktmo']),'OKATO_to_OKTMO transition_or_binding_claimed':False,'opaque_historical_record_id_continuity_claimed':False,'physical_point_witnesses':{'GeoNames_raw_id_locator':gn['geonameid'],'GeoNames_feature_code':gn['feature_code'],'GeoNames_to_2011_point_km':round(dist,6),'RCSI_support_km':round(hav(gn['latitude'],gn['longitude'],rcsi['latitude'],rcsi['longitude']),6) if target_name=='SUPS' else None},'current_raw_publisher_point_used':False,'population_used_as_identity_evidence':False,'event_or_legal_date_claimed':False},ensure_ascii=False,sort_keys=True)})
  origin=str(GNZIP);locator=f"member=RU.txt;line={gn['line']};byte_start={gn['byte_start']};byte_end={gn['byte_end']};line_sha256_including_lf={gn['line_sha256']}"
  # The accepted tenth baseline already contains the 2002 and 2010 GeoKLADR
  # point uses. Record those as corroborating prior state, but stage only the
  # missing 2021 retrospective physical-place point use to avoid duplicate rows.
  for year in [2021]:
   target=srcids[year];pathids=[] if year==2021 else ([f'{target_name}-E-2010-2021'] if year==2010 else [f'{target_name}-E-2002-2010',f'{target_name}-E-2010-2021'])
   points.append({'point_use_id':f'{target_name}-P-{year}','target':target_name_ru,'target_source_record_id':target,'target_year':year,'latitude':gn['latitude'],'longitude':gn['longitude'],'coordinate_source':'GeoNames RU exact native-language-alias physical settlement PPL point, selected through scoped classifier/point concordance review','coordinate_provider_id':None,'provider_binding_status':'GeoNames ID is only a raw row locator; provider/entity binding is not asserted','coordinate_admission_status':'independently_reviewed_candidate_for_root_application','coordinate_quality':'independent_named_typed_classifier_and_locality_concordant_settlement_point','coordinate_measurement_date_unknown':True,'coordinate_precision_claimed':False,'boundary_comparability_asserted':False,'historical_coordinate_measurement_asserted':False,'point_origin_file':origin,'point_origin_sha256':EXPECTED['gnzip'],'point_origin_member_sha256':'3ef8f69d9c6b8adbd53afc35f6dc774b1d01b04f566622e1892a6d2f00d2f4d0','point_origin_locator':locator,'point_origin_line_sha256':gn['line_sha256'],'point_origin_raw_line':gn['raw_line'],'geonameid_raw_locator_only':gn['geonameid'],'supporting_2009_sql_code_literal':sqlrows[target_name]['okato'],'supporting_2011_dbf_code_literal':dbfrows[target_name]['okato_literal'],'supporting_2011_dbf_raw_point_distance_km':round(dist,6),'supporting_RCSI_local_point_distance_km':round(hav(gn['latitude'],gn['longitude'],rcsi['latitude'],rcsi['longitude']),6) if target_name=='SUPS' else None,'source_current_wrong_shared_point_retained_not_used':True,'same_place_path_ids_json':json.dumps(pathids),'inference_kind':'direct current independent physical PPL point candidate' if year==2021 else 'retrospective physical continuity through the two reviewed candidate same_place edges','population_context_only':float(sel[srcids[year]]['population'])})
 holds=[
  {'target':'Гостагаевская','scope':'raw current DaData coordinates','status':'retained but not selected as accepted point use','reason':'Exact current raw point is shared with the distinct current Supsekh source ID and is approximately 20 km from the independently concordant named classifier/GN locality. Raw source coordinate claim is preserved unchanged.'},
  {'target':'Гостагаевская','scope':'GeoNames RSTN 826098','status':'excluded feature class','reason':'Exact alias is a separate railway-station RSTN feature with expanded station label, not the P/PPL settlement feature.'},
  {'target':'Супсех','scope':'GeoNames PPL 867470','status':'retained as alternate point feature; not selected','reason':'Same exact alias, but 2.098626 km from the uniquely coded 2011 locality and 1.471008 km from the independently sourced RCSI village point; not evidence of a second formal settlement.'},
  {'target':'Супсех','scope':'GeoNames PPLX 866252','status':'excluded from settlement-point selection','reason':'Different physical feature class/grain; exact alias alone does not make it the formal village point.'},
  {'target':'Супсех','scope':'raw current DaData coordinates','status':'retained but not selected as accepted point use','reason':'Exact current raw coordinate is shared with the distinct Gostagaevskaya source ID and 5.610283 km from the coded physical locality point; source record and value remain unchanged.'},
 ]
 OUT.mkdir(parents=True)
 def writecsv(name,rows):
  path=OUT/name;fields=list(rows[0]) if rows else ['status'];
  with path.open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
  return path
 written={}
 for name,data in [('eligible_identity_edges.csv',edge_rows),('eligible_point_uses.csv',points),('holds_and_exclusions.csv',holds),('publisher_context_replay.csv',years_check),('legacy_event_flag_replay.csv',event_audit)]:written[name]=writecsv(name,data)
 support={'historical_2002_raw_rows':x2002,'primary_2010_pdf_rows':pdf_rows,'classifier_2009_sql_rows':sqlrows,'classifier_2011_dbf_rows':dbfrows,'raw_current_publisher_rows':rawcurrent,'geonames_exact_features':gn_by_id,'supsekh_rcsi_raw_row':rcsi,'accepted_historical_point_use_rows_before_review':accepted_points,'database_point_distance_km':round(dbf_distance,6),'native_code_frequencies_used_only_for_row_disambiguation':{x['target_name']:x['current_native_id_frequency_2021'] for x in idctx},'existing_graph_edges_on_reviewed_ids':relevant,'qid_binding_results':qid,'supsekh_ambiguous_feature_rows':feat}
 support_path=OUT/'raw_evidence_replay.json';support_path.write_text(json.dumps(support,ensure_ascii=False,indent=2)+'\n');written['raw_evidence_replay.json']=support_path
 output_pins={n:{'path':str(p),'sha256':sha(p),'rows':sum(1 for _ in open(p,encoding='utf-8'))-1 if n.endswith('.csv') else None} for n,p in written.items()}
 receipt={'status':'independent_finite_identity_and_point_review_complete_candidate_only','review_scope':'Гостагаевская and Супсех as separate exact typed physical settlements; administrative boundaries remain un-equated','review_decision':'four same_place edge candidates and two missing 2021 point-use candidates eligible for root-side batch application, subject to final integration review. Four historical 2002/2010 point uses were already accepted on the pinned baseline and are not duplicated.','baseline_graph_sha256':EXPECTED['graph'],'baseline_point_ledger_sha256':EXPECTED['latest_points'],'baseline_point_rows':pq.ParquetFile(POINTS).metadata.num_rows,'already_accepted_historical_point_use_rows':len(accepted_points),'input_pins':input_pins,'independent_raw_replay':{'2002_exact_rows':{'Гостагаевская':'XLS sheet 11 row 359; printed row 358 is Гостагаевский сельский округ; count 8962','Супсех':'XLS sheet 11 row 392; count 6335'},'2010_exact_rows':{'Гостагаевская':'official primary Tom 1 Table 5 page 76 line; count 9772 under Anapa district rural population heading','Супсех':'official primary Tom 1 Table 5 page 76 line; count 6669 under Anapa district rural population heading'},'2021_exact_rows':{'Гостагаевская':'Tochno parquet row 46763, native OKTMO 3703000181 unique/disambiguator only; source raw coordinate is shared and not used','Супсех':'Tochno parquet row 46789, native OKTMO 3703000311 unique/disambiguator only; source raw coordinate is shared and not used'},'classifier_concordance':'2009 SQL and 2011 GeoKLADR raw rows repeat each named locality’s literal old OKATO and printed type; existing accepted 2011 points remain source coordinates, not newly inferred historical measurements.','chosen_points':{'Гостагаевская':'GeoNames RU.txt line 98324, alias Гостагаевская, P/PPL, ADM1 38, coordinate 45.02284,37.50511; 0.507667 km from typed 2011 physical row','Супсех':'GeoNames RU.txt line 25650, exact alias Супсех, P/PPL, coordinate 44.86285,37.36629; 0.34789 km from typed 2011 physical row and 0.748536 km from RCSI village point'},'administrative_context':'2002/2010/2021 raw district and municipal labels are retained per observation; no boundary equivalence is asserted.'},'candidate_edge_count':len(edge_rows),'candidate_point_use_count':len(points),'candidate_population_context_only_sum':sum(float(r['population_context_only']) for r in points),'hold_count':len(holds),'source_event_resolution':'Only the exact old administrative_conflict legacy quarantine is resolved for these exact proposed pairs through independently replayed source/type/classifier/point evidence. Existing source flags are preserved; no general legacy-flag clearance.','provider_binding_asserted':False,'population_changed':False,'accepted_graph_mutated':False,'accepted_point_ledger_mutated':False,'selected_observations_mutated':False,'source_evidence_mutated':False,'coordinate_measurement_date_or_precision_claimed':False,'boundary_comparability_claimed':False,'input_method_pins':{'producer_script_sha256':'37905f0a695745981be7990f29019bce1a38d57d76f083dde755a6af6ade2dc9','source_evidence_sha256':EXPECTED['source_evidence']},'outputs':output_pins}
 rp=OUT/'independent_review_receipt.json';rp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'receipt_path':str(rp),'receipt_sha256':sha(rp),'outputs':output_pins,'decision':receipt['review_decision'],'baseline_point_rows':receipt['baseline_point_rows']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
