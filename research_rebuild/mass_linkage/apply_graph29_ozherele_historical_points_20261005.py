#!/usr/bin/env python3
"""Apply reviewed 2011 GeoKLADR points to the two historical Ozherele rows.

Point-only extension for 2002 and 2010. It adds no 2021/Kashira identity edge,
no population values, and no population or boundary comparability assertion.
"""
from __future__ import annotations
import hashlib, json, struct, subprocess
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT=Path('/workspace')
SELECTED=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GRAPH=Path('/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet')
POINTS=Path('/tmp/graph28_three_code_bridge_20261005/accepted_point_uses.parquet')
XLS2002=ROOT/'settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls'
PDF2010=ROOT/'settlements-raw/data/raw/2010_official_tom11/pub-11-1-4.pdf'
OKATO=ROOT/'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
DBF=ROOT/'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
OUT=Path('/tmp/graph29_ozherele_points_20261005')
IDS={2002:'2002:1_TOM_01_04.xls:0:1133',2010:'2010:pub-11-1-4.pdf:pdf_page_13:25'}
POPS={2002:11113,2010:10469}
CODE8='46220504'; CODE11='46220504000'; NAME='Ожерелье'; LAT=54.803036; LON=38.273946
EXPECTED={
 'selected':'4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
 'graph':'583364c80cddc4fbed00dd06527f734242b1983c268f83a78a38946a811ede1d',
 'points':'e4c8de5891a179057356d357e564e5928e0d0113519e8b9e8f1152df8ef479fb',
 'xls2002':'745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3',
 'pdf2010':'db2528e6db3c6089351bd09d253c9dfa607e2f2dff6cc45d1174fb21fa96d500',
 'okato':'6062e097ad504ba8b4bc130599ca4825c54f2b98486d16aed15ac143fcd705db',
 'dbf':'d1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650',
}

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def dbf_read(path:Path,nrec:int):
 d=path.read_bytes(); count=struct.unpack('<I',d[4:8])[0]; hlen=struct.unpack('<H',d[8:10])[0]; rlen=struct.unpack('<H',d[10:12])[0]
 if not (1<=nrec<=count):raise ValueError('DBF record out of range')
 off=hlen+(nrec-1)*rlen;r=d[off:off+rlen];fields=[];i=32;start=1
 while i+32<=hlen-1 and d[i]!=13:
  f=d[i:i+32]; nm=f[:11].split(b'\0')[0].decode('ascii','replace');w=f[16];fields.append((nm,w,start));start+=w;i+=32
 row={nm:r[b:b+w].decode('cp1251','replace').strip() for nm,w,b in fields}
 return row,off

def main():
 if OUT.exists():raise FileExistsError(OUT)
 inputs={'selected':SELECTED,'graph':GRAPH,'points':POINTS,'xls2002':XLS2002,'pdf2010':PDF2010,'okato':OKATO,'dbf':DBF}
 for k,p in inputs.items():
  actual=sha(p)
  if actual!=EXPECTED[k]:raise ValueError(f'{k} SHA mismatch: {actual}')
 sel=pd.read_parquet(SELECTED,columns=['source_record_id','census_year','settlement_name','settlement_type','region_norm','population','population_value_quality','is_additive_settlement_record','population_scope','source_file','source_sheet','source_row'])
 sel=sel.set_index('source_record_id',drop=False)
 expected_quality={2002:'direct_published_census_value',2010:'direct_official_city_value'}
 for year,sid in IDS.items():
  r=sel.loc[sid]
  if (int(r.census_year),str(r.settlement_name),str(r.settlement_type),int(r.population),str(r.population_value_quality),bool(r.is_additive_settlement_record),str(r.population_scope)) != (year,NAME,'город',POPS[year],expected_quality[year],True,'settlement'):
   raise ValueError(f'selected row mismatch: {sid}')
 xls=pd.read_excel(XLS2002,sheet_name=0,header=None)
 v=xls.iloc[1132].tolist()
 if str(v[0]).strip()!='г. Ожерелье' or int(v[1])!=11113:raise ValueError('2002 TOM raw row mismatch')
 txt=subprocess.run(['pdftotext','-layout','-f','13','-l','13',str(PDF2010),'-'],check=True,capture_output=True,text=True).stdout
 if not any(line.strip().split()[:2]==['Ожерелье','Московская'] and line.split()[-2:]==['11113','10469'] for line in txt.splitlines()):raise ValueError('2010 official PDF row mismatch')
 sql=OKATO.read_text(encoding='utf-8',errors='replace').splitlines()
 hits=[(i+1,x) for i,x in enumerate(sql) if x.split('\t',1)[0].strip()==CODE8]
 if len(hits)!=1 or hits[0][0]!=97200:raise ValueError('2009 OKATO code nonunique or wrong locator')
 cols=hits[0][1].split('\t')
 if cols[1:3]!=[NAME,NAME] or cols[3].strip()!='город' or cols[-1].strip().lower()!='t':raise ValueError('2009 OKATO name/type/status mismatch')
 dbf,offset=dbf_read(DBF,72730)
 if offset!=28728660 or dbf['TER']+dbf['KOD1']+dbf['KOD2']+dbf['KOD3']!=CODE11 or dbf['KOD3']!='000' or dbf['NAME1']!=NAME or dbf['SCOKATO']!='г' or dbf['LAT']!='54.803036' or dbf['LONG']!='38.273946':raise ValueError('GeoKLADR raw row mismatch')
 allrows=DBF.read_bytes(); nrec=struct.unpack('<I',allrows[4:8])[0]; hlen=struct.unpack('<H',allrows[8:10])[0];rlen=struct.unpack('<H',allrows[10:12])[0]
 code_matches=[];name_matches=[]
 for i in range(nrec):
  off=hlen+i*rlen;rec=allrows[off:off+rlen];
  if rec[:1]==b'*':continue
  # relevant field offsets are obtained from the exact candidate row; unique full code is already checked by full scan below via DBF fields.
  if rec[1:1+11].decode('cp1251','replace').strip()==CODE11:code_matches.append(i+1)
 if code_matches != [72730]:raise ValueError(f'full-code DBF uniqueness failed: {code_matches[:10]}')
 graph=pd.read_parquet(GRAPH)
 pair_edges=graph.loc[graph.relation.eq('same_place') & graph.decision_status.isin({'checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted','case_review_accepted','independent_case_review_accepted','accepted_case_specific'})]
 pair=pair_edges.loc[pair_edges.decision_id.astype(str).eq('TOM11-BRIDGE-2fbf8b3f501c194f5f201182')]
 if len(pair)!=1 or set(pair[['from_source_record_id','to_source_record_id']].astype(str).iloc[0])!=set(IDS.values()):raise ValueError('existing exact 2002-2010 identity edge absent')
 points=pd.read_parquet(POINTS); existing=set(points.target_source_record_id.astype(str))
 if existing & set(IDS.values()):raise ValueError('historical target unexpectedly already has accepted point')
 schema=pq.read_schema(POINTS); template=points.iloc[0].to_dict();new=[]
 for year,sid in IDS.items():
  s=sel.loc[sid];row={k:(None if pd.isna(v) else v) for k,v in template.items()}
  row.update({'target_source_record_id':sid,'target_year':f'{year}.0','latitude':LAT,'longitude':LON,
   'coordinate_quality':'independently_reviewed_historical_named_point_code_bridge',
   'coordinate_source':'GeoKLADR 2011 named city representative point; exact 2009 OKATO to 2011 GeoKLADR code bridge',
   'coordinate_source_record_id':'GeoKLADR2011:OKATO:'+CODE11,'coordinate_provider':'GeoKLADR 2011 raw locality DBF',
   'source_name':NAME,'source_type':'город','source_region':'Московская область',
   'source_file':str(s.source_file),'source_row':float(s.source_row),
   'source_sha256':EXPECTED['xls2002'] if year==2002 else EXPECTED['pdf2010'],
   'source_locator':f"{s.source_sheet}:{int(s.source_row)}; selected ID={sid}",
   'coordinate_provenance':f'One unique named 2011 GeoKLADR row for Ожерелье, raw OKATO 46220504 → GeoKLADR {CODE11}; representative point {LAT},{LON}. DATA_UPD is 2011-06-20, not a physical measurement date.',
   'admission_rule':'exact selected historical city row + active bounded 2002-2010 same_place component + unique exact 2009 OKATO/2011 GeoKLADR named typed code and point',
   'provider_binding_status':'No external provider ID asserted; point belongs to exact named GeoKLADR row.',
   'provider_fias_binding_status':'No FIAS/provider ID asserted.','coordinate_admission_status':'reviewed_case_accepted',
   'coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,
   'coordinate_application_family':'graph29_ozherele_historical_point_reuse_20261005',
   'review_id':'independent_historical_named_point_review_ozherele_20261005',
   'application_inference_kind':'historical_named_place_representative_point_code_bridge',
   'direct_historical_coordinate_measurement':False,'population_scope_comparability_asserted':False,
   'admission_allowed':True,'coordinate_admitted':True,'point_admitted':True,'identity_edge_admitted':False,
   'historical_propagation_allowed':True,'coordinate_source_sha256':EXPECTED['dbf'],
   'coordinate_source_locator':'DBF record 72730; byte offset 28728660; OKATO SQL line 97200',
   'coordinate_source_file':str(DBF),'coordinate_source_origin':'GeoKLADR 2011 named locality representative point; measurement date unknown',
   'coordinate_source_input_artifact_sha256':EXPECTED['okato'],'coordinate_source_date':'2011 edition; measurement date unknown',
   'coordinate_source_latitude_raw':dbf['LAT'],'coordinate_source_longitude_raw':dbf['LONG'],
   'point_origin_file':str(DBF),'point_origin_sha256':EXPECTED['dbf'],'point_origin_locator':'record=72730;byte_offset=28728660',
   'point_origin_kind':'geokladr_2011_raw_dbf_coordinate','point_use_id':f'graph29-ozherele:{year}:{sid}',
   'population':POPS[year],'supporting_2009_sql_code_literal':CODE8,'supporting_2011_dbf_code_literal':CODE11,
   'supporting_2011_dbf_raw_point_distance_km':'0','historical_identity_asserted':'2002 and 2010 only; no 2021/Kashira edge',
   'native_identifier_binding_asserted':'exact 2009 OKATO to 2011 GeoKLADR code; no modern provider ID asserted',
   'census_date_measurement_asserted':'false','point_origin_row_1based':'72730','point_origin_raw_payload_sha256':EXPECTED['dbf'],
   'source_raw_object_level':'named historical city row with selected settlement scope',
   'boundary_comparability':'not asserted','historical_reuse':'same named physical city point reused for selected 2002 and 2010 rows only',
   'coordinate_uncertainty_flags_json':json.dumps({'measurement_date_unknown':True,'boundary_comparability_not_asserted':True,'2021_identity_not_asserted':True},sort_keys=True),
   'target_source_name_raw':str(s.source_file)+'; exact selected row'})
  for f in schema:
   v=row.get(f.name)
   if v is None or pd.isna(v):row[f.name]=None
   elif pa.types.is_string(f.type) or pa.types.is_large_string(f.type):row[f.name]=str(v)
   elif pa.types.is_boolean(f.type):row[f.name]=bool(v)
   elif pa.types.is_integer(f.type):row[f.name]=int(v)
   elif pa.types.is_floating(f.type):row[f.name]=float(v)
  new.append(row)
 OUT.mkdir(parents=True); out=OUT/'accepted_point_uses.parquet';w=pq.ParquetWriter(out,schema,compression='zstd')
 base=pq.ParquetFile(POINTS)
 for b in base.iter_batches(batch_size=25000):w.write_batch(b)
 w.write_table(pa.Table.from_pylist(new,schema=schema));w.close()
 receipt={'status':'two_accepted_historical_ozherele_point_uses_applied','inputs':{k:{'path':str(v),'sha256':sha(v)} for k,v in inputs.items()},'target_rows':[{'year':y,'source_record_id':sid,'population':POPS[y],'population_value_unchanged':True} for y,sid in IDS.items()],'point':{'latitude':LAT,'longitude':LON,'code_2009_okato':CODE8,'code_2011_geokladr':CODE11,'dbf_record_1based':72730,'dbf_offset_0based':28728660,'measurement_date_unknown':True},'existing_identity_link':'TOM11-BRIDGE-2fbf8b3f501c194f5f201182','added_identity_edges':0,'added_point_uses':2,'no_2021_or_kashira_edge':True,'population_comparability_asserted':False,'boundary_comparability_asserted':False,'existing_coordinate_conflicts':0,'output':{'path':str(out),'sha256':sha(out),'rows':pq.ParquetFile(out).metadata.num_rows},'limitations':['No 2021 edge: later inclusion in Kashira remains separately scoped and its legal effective date is not asserted.','The 2011 GeoKLADR DATA_UPD is not the physical coordinate measurement date.','Coordinate reuse does not imply comparable census population boundaries.']}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
