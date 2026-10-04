#!/usr/bin/env python3
"""Independent raw-source review of candidate-only rural historical point uses."""
from __future__ import annotations
import csv, hashlib, json, re, unicodedata
from collections import Counter
from pathlib import Path
import duckdb, pandas as pd, xlrd

BASE=Path('/workspace/settlements-work/continuation_20261004')
SRC=BASE/'root/R4/historical_points/rural_native_extension/source_evidence_verified_final'
OUT=BASE/'root/R4/independent_rural_and_type_review/rural_native_point_review'
LEDGER=SRC/'rural_native_candidate_ledger.parquet'
POINTS=SRC/'rural_native_staged_point_uses.parquet'
FROZEN=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
SELECTED=FROZEN/'selected_observations.parquet'
SOURCES=Path('/workspace/settlements-raw')
SQL=Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql')
DBF=Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
SQL_SHA='6062e097ad504ba8b4bc130599ca4825c54f2b98486d16aed15ac143fcd705db'
DBF_SHA='d1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650'
EXPECTED_POINTS='e7ef14902a19352b31ab91bacc221dd81ba7c6af8fbb28161659fec8c55b67bc'

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def norm(v):
 if pd.isna(v): return ''
 return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е')).strip()
def num(v):
 try:
  if v is None or str(v).strip()=='':return None
  return float(str(v).strip().replace(',','.'))
 except:return None
def norm_admin(v):
 s=norm(v).replace('.','').replace('(',' ').replace(')',' ')
 s=re.sub(r'\s+',' ',s).strip()
 for suffix in [' край',' область',' обл',' республика',' автономный округ']:
  if s.endswith(suffix): s=s[:-len(suffix)].strip()
 s={'удмуртия':'удмуртская','якутия':'саха якутия'}.get(s,s)
 return s
def dbf_layout(path):
 b=path.read_bytes(); hl=int.from_bytes(b[8:10],'little'); rl=int.from_bytes(b[10:12],'little'); fs=[]; pos=1
 for off in range(32,hl-1,32):
  d=b[off:off+32]
  if not d or d[0]==0x0d:break
  name=d[:11].split(b'\0',1)[0].decode('ascii');ln=d[16];fs.append((name,pos,ln));pos+=ln
 return b,hl,rl,fs
def dbf_record(layout, recno):
 b,hl,rl,fs=layout; off=hl+(int(recno)-1)*rl; raw=b[off:off+rl]
 out={'_deleted':raw[:1]==b'*','_offset':off}
 for name,pos,ln in fs:
  x=raw[pos:pos+ln].strip()
  try: out[name]=x.decode('cp1251').strip()
  except UnicodeDecodeError: out[name]=x.decode('cp866','replace').strip()
 return out
def sql_line(path, n):
 with path.open('r',encoding='utf-8') as f:
  for i,line in enumerate(f,1):
   if i==int(n):return line.rstrip('\r\n').split('\t')
 raise IndexError(n)

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 assert sha(SQL)==SQL_SHA and sha(DBF)==DBF_SHA
 assert sha(POINTS)==EXPECTED_POINTS
 con=duckdb.connect()
 l=con.execute("select * from read_parquet(?) where decision_status='point_only_candidate_pending_independent_review'",[str(LEDGER)]).df()
 p=con.execute('select * from read_parquet(?)',[str(POINTS)]).df()
 assert len(l)==402 and len(p)==402
 assert p.target_source_record_id.nunique()==402
 assert p[['target_source_record_id','target_year']].merge(l[['target_source_record_id','target_year']],on=['target_source_record_id','target_year'],how='outer',indicator=True)._merge.eq('both').all()
 # Selected source rows are the immutable census basis. Check selected input and
 # all 402 actual workbook rows independently rather than trusting producer flags.
 selected=con.execute('select * from read_parquet(?)',[str(SELECTED)]).df()
 selected['review_key']=(selected.census_year.astype(str)+'\x1f'+selected.settlement_name.map(norm)+'\x1f'+selected.settlement_type.map(norm)+'\x1f'+selected.region_raw.map(norm))
 key_counts=selected.groupby('review_key').source_record_id.nunique()
 selected=selected[selected.source_record_id.isin(l.target_source_record_id)].copy()
 assert len(selected)==402 and selected.source_record_id.nunique()==402
 byid=selected.set_index('source_record_id')
 books={}; source_hash_cache={}; workbook_results=[]
 for r in l.itertuples(index=False):
  x=r._asdict(); path=SOURCES/x['selected_source_file']
  if x['selected_source_file'] not in books:
   books[x['selected_source_file']]=xlrd.open_workbook(str(path),on_demand=True)
  actual_hash=source_hash_cache.setdefault(x['selected_source_file'],sha(path))
  book=books[x['selected_source_file']]; sh=book.sheet_by_name(x['selected_source_sheet']); row=sh.row_values(int(x['selected_source_row_1based'])-1)
  check=json.loads(x['source_raw_row_check_json']); cells=check['cells']
  # Layouts differ by source workbook. Locate name/population by their exact
  # frozen row-check witnesses; never assume cells 3/5 are admin fields.
  expected_name=str(check.get('source_name_raw_expected',x['source_raw_name_selected']))
  name_positions=[i for i,v in enumerate(row) if norm(v)==norm(expected_name)]
  pop_start=(name_positions[0]+1) if len(name_positions)==1 else 0
  pop_positions=[i for i,v in enumerate(row) if i>=pop_start and num(v) is not None and int(num(v))==int(x['population'])]
  rawname=str(row[name_positions[0]]).strip() if len(name_positions)==1 else ''
  rawpop=num(row[pop_positions[0]]) if len(pop_positions)>=1 else None
  region_positions=[i for i,v in enumerate(row) if norm_admin(v)==norm_admin(x['source_region_raw']) and str(v).strip()]
  district_positions=[i for i,v in enumerate(row) if norm(v)==norm(x['source_district_raw']) and str(v).strip()]
  region=str(row[region_positions[0]]).strip() if len(region_positions)>=1 and bool(x['direct_source_row_region_cell_witness']) else ''
  district=str(row[district_positions[0]]).strip() if len(district_positions)>=1 and bool(x['direct_source_row_district_cell_witness']) else ''
  fr=byid.loc[x['target_source_record_id']]
  source_hash_ok=(actual_hash==x['selected_source_file_sha256_manifest']==x['selected_source_file_sha256_local'])
  selected_key=x['target_year'].__str__()+'\x1f'+norm(x['settlement_name'])+'\x1f'+norm(x['settlement_type'])+'\x1f'+norm(x['source_region_raw'])
  selected_match=(int(fr.census_year)==int(x['target_year']) and norm(fr.settlement_name)==norm(x['settlement_name'])
    and norm(fr.settlement_type)==norm(x['settlement_type']) and num(fr.population)==num(x['population'])
    and str(fr.source_file)==x['selected_source_file'] and str(fr.source_sheet)==x['selected_source_sheet']
    and int(fr.source_row)==int(x['selected_source_row_1based']) and source_hash_ok)
  workbook_results.append({'target_source_record_id':x['target_source_record_id'],'source_file':x['selected_source_file'],'source_sha256':actual_hash,
   'sheet':x['selected_source_sheet'],'row_1based':int(x['selected_source_row_1based']),'raw_label':rawname,'raw_population':rawpop,
   'raw_region_cell':region,'raw_district_cell':district,'direct_region_cell_status':('observed' if region else ('unknown_not_forwardfilled' if not bool(x['direct_source_row_region_cell_witness']) else 'present_but_unparsed')),
   'direct_district_cell_status':('observed' if district else ('unknown_not_forwardfilled' if not bool(x['direct_source_row_district_cell_witness']) else 'present_but_unparsed')),
   'label_matches_selected_candidate':len(name_positions)==1 and norm(rawname)==norm(x['source_raw_name_selected']),
  'population_matches_selected_candidate':len(pop_positions)>=1 and rawpop is not None and int(rawpop)==int(x['population']),
   'selected_source_file_hash_matches_manifest_and_selected_row':bool(source_hash_ok),
   'selected_full_table_region_name_type_key_unique':int(key_counts.get(selected_key,0))==1,
   'selected_frozen_row_matches_candidate':bool(selected_match),'row_witness_json_label_pop_exact':bool(check.get('name_exact') and check.get('population_exact')),
   'direct_region_cell_present':bool(region),'direct_district_cell_present':bool(district),
   'admin_blanks_kept_unknown':((not bool(x['direct_source_row_region_cell_witness']) or region_positions.__len__()>=1)
     and (not bool(x['direct_source_row_district_cell_witness']) or district_positions.__len__()>=1))})
 # Raw 2009 tabular SQL and 2011 DBF exact record checks for every candidate.
 dbfl=dbf_layout(DBF); raw_results=[]
 sql_code_counts=Counter(line.split('\t',1)[0].strip() for line in SQL.open('r',encoding='utf-8') if line.strip())
 _dbbytes,_dbheader,_dbrecord,_dbfields=dbfl
 dbf_code_counts=Counter()
 for recno in range(1,int.from_bytes(_dbbytes[4:8],'little')+1):
  rec=dbf_record(dbfl,recno)
  if not rec['_deleted']:
   rawcode=''.join(str(rec.get(k,'')) for k in ['TER','KOD1','KOD2','KOD3'])
   if rawcode:dbf_code_counts[rawcode]+=1
 for r in l.itertuples(index=False):
  x=r._asdict(); sqlr=sql_line(SQL,x['historical_classifier_sql_line_1based']); d=dbf_record(dbfl,x['geokladr_record_1based'])
  code=str(x['historical_okato2009_raw']); dbcode=''.join(str(d.get(k,'')) for k in ['TER','KOD1','KOD2','KOD3'])
  sql_code=str(sqlr[0]).zfill(11) if sqlr else ''
  sql_ok=(len(sqlr)>=6 and sql_code==str(code).zfill(11) and sqlr[1]==x['classifier_raw_name'] and sqlr[3]==x['classifier_raw_status'] and sqlr[5]=='t')
  # The DBF has no textual type label field; preserve its raw TYPE_NP code and
  # compare the literal NAME1 to the independently parsed SQL name.
  dbf_ok=(not d['_deleted'] and int(d['_offset'])==int(x['geokladr_byte_offset_0based']) and dbcode==str(x['geokladr_okato2011_raw']).zfill(11)==str(code).zfill(11)
   and d['NAME1']==x['geokladr_name_raw'] and num(d['LAT'])==num(x['geokladr_lat_raw']) and num(d['LONG'])==num(x['geokladr_lon_raw'])
   and str(d['DATA_UPD'])==str(x['geokladr_data_upd_raw']))
  coords_match=(num(x['latitude'])==num(d['LAT']) and num(x['longitude'])==num(d['LONG']) and num(x['latitude']) is not None and num(x['longitude']) is not None)
  # Same code, source type text and raw place name have to concord across 2009
  # classifier and 2011 DBF; abbreviations are retained verbatim for review.
  classifier_dbf_name_same=norm(sqlr[1])==norm(d['NAME1'])
  selected_type_matches_2009=norm(x['settlement_type'])==norm(sqlr[3])
  raw_results.append({'target_source_record_id':x['target_source_record_id'],'year':int(x['target_year']),'code_2009':sqlr[0] if sqlr else '',
   'code_2011':dbcode,'sql_line_1based':int(x['historical_classifier_sql_line_1based']),'dbf_record_1based':int(x['geokladr_record_1based']),
   'dbf_byte_offset_0based':int(x['geokladr_byte_offset_0based']),'sql_2009_exact_code_name_status_rural':bool(sql_ok),
   'dbf_2011_exact_code_raw_name_coordinates_date':bool(dbf_ok),'classifier_dbf_name_normalized_equal':bool(classifier_dbf_name_same),
   'sql_2009_code_unique_in_full_source':sql_code_counts[sqlr[0]]==1,
   'dbf_2011_code_unique_in_full_source':dbf_code_counts[dbcode]==1,
   'raw_point_coordinates_match_dbf':bool(coords_match),'selected_type_matches_2009_classifier':bool(selected_type_matches_2009),
   'dbf_name':d['NAME1'],'dbf_type_np_raw':d['TYPE_NP'],'dbf_lat':num(d['LAT']),'dbf_lon':num(d['LONG']),
   'point_source_file':str(DBF),'point_source_sha256':sha(DBF),'point_source_locator':f"okato.dbf:record={int(x['geokladr_record_1based'])};byte_offset={int(x['geokladr_byte_offset_0based'])};OKATO11={code}",
   'candidate_source_native_id_opaque_not_code':x['source_native_id_opaque_not_code'],'native_id_not_compared_as_OKATO':True})
 wb=pd.DataFrame(workbook_results); rr=pd.DataFrame(raw_results)
 wb.to_csv(OUT/'selected_census_raw_row_review.csv',index=False,encoding='utf-8',quoting=csv.QUOTE_MINIMAL,lineterminator='\n')
 rr.to_csv(OUT/'raw_2009_2011_fullvector_review.csv',index=False,encoding='utf-8',quoting=csv.QUOTE_MINIMAL,lineterminator='\n')
 # This independent stage carries no identity or measurement-date admission.
 out=l.merge(p,on=['target_source_record_id','target_year'],suffixes=('_ledger','_point'))
 for col in ['coordinate_quality','coordinate_admission_status','coordinate_source','coordinate_provider',
             'coordinate_source_record_id','coordinate_provenance']:
  if f'{col}_point' in out.columns:out[col]=out[f'{col}_point']
 out['point_source_file']=out['point_origin_file'];out['point_source_sha256']=out['point_origin_sha256'];out['point_source_locator']=out['point_origin_locator']
 out['coordinate_admission_rule']=out['admission_rule']
 keep=['target_source_record_id','target_year','population','settlement_name','settlement_type','source_region_raw','source_district_raw',
   'source_native_id_opaque_not_code','historical_okato2009_raw','classifier_raw_name','classifier_raw_status','historical_classifier_sql_line_1based',
   'geokladr_okato2011_raw','geokladr_name_raw','geokladr_type_raw','geokladr_record_1based','geokladr_byte_offset_0based','geokladr_lat_raw','geokladr_lon_raw',
   'latitude_point','longitude_point','coordinate_quality','coordinate_admission_status','coordinate_temporal_basis','coordinate_source','coordinate_provider',
   'coordinate_source_record_id','coordinate_provenance','point_source_file','point_source_sha256','point_source_locator','coordinate_admission_rule',
   'point_origin_kind','historical_classifier2009_file','historical_classifier2009_sha256','historical_classifier2009_locator',
   'direct_source_row_region_cell_witness','direct_source_row_district_cell_witness','admin_context_interpretation','legacy_identity_conflict_preserved_not_decided_by_point',
   'temporal_identity_admitted','modern_point_continuity_admitted','population_boundary_comparability_asserted','census_date_coordinate_claimed']
 # normalize coordinate column names after ledger/point merge
 for a,b in [('latitude','latitude_point'),('longitude','longitude_point')]:
  if a in out.columns and b not in out.columns: out.rename(columns={a:b},inplace=True)
 elig=out.merge(wb[['target_source_record_id','label_matches_selected_candidate','population_matches_selected_candidate','selected_source_file_hash_matches_manifest_and_selected_row','selected_full_table_region_name_type_key_unique','selected_frozen_row_matches_candidate','admin_blanks_kept_unknown','raw_region_cell','raw_district_cell','direct_region_cell_status','direct_district_cell_status']],on='target_source_record_id')
 elig=elig.merge(rr[['target_source_record_id','code_2009','code_2011','sql_2009_exact_code_name_status_rural','dbf_2011_exact_code_raw_name_coordinates_date','classifier_dbf_name_normalized_equal','raw_point_coordinates_match_dbf','selected_type_matches_2009_classifier','sql_2009_code_unique_in_full_source','dbf_2011_code_unique_in_full_source']],on='target_source_record_id')
 elig['historical_okato2009_raw']=elig['code_2009'].astype(str)
 elig['geokladr_okato2011_raw']=elig['code_2011'].astype(str)
 checks=['label_matches_selected_candidate','population_matches_selected_candidate','selected_source_file_hash_matches_manifest_and_selected_row','selected_full_table_region_name_type_key_unique','selected_frozen_row_matches_candidate','admin_blanks_kept_unknown','sql_2009_exact_code_name_status_rural','dbf_2011_exact_code_raw_name_coordinates_date','classifier_dbf_name_normalized_equal','raw_point_coordinates_match_dbf','selected_type_matches_2009_classifier','sql_2009_code_unique_in_full_source','dbf_2011_code_unique_in_full_source']
 elig['independent_rural_point_review_status']=elig[checks].all(axis=1).map({True:'eligible_point_only_independent_raw_review_pass',False:'held_independent_raw_review_mismatch'})
 elig['interpretation']='Retrospective point for selected census record by exact 2009/2011 named rural place code/name concordance; source native ID opaque; historic observation date/scope and census identity not asserted.'
 result=elig.independent_rural_point_review_status.eq('eligible_point_only_independent_raw_review_pass')
 eligible=elig[result].copy()
 keep=[c for c in keep if c in elig.columns]+['raw_region_cell','raw_district_cell','direct_region_cell_status','direct_district_cell_status']+checks+['independent_rural_point_review_status','interpretation']
 elig[keep].to_csv(OUT/'independent_rural_point_eligibility.csv',index=False,encoding='utf-8',quoting=csv.QUOTE_MINIMAL,lineterminator='\n')
 ids=eligible[['target_source_record_id','target_year','population','latitude_point','longitude_point','historical_okato2009_raw','geokladr_okato2011_raw','point_source_file','point_source_sha256','point_source_locator','coordinate_admission_rule']].copy()
 ids['point_candidate_input_file']=str(POINTS);ids['point_candidate_input_sha256']=sha(POINTS)
 ids['independent_review_status']='eligible_point_only_independent_raw_review_pass'
 ids.to_csv(OUT/'eligible_point_candidate_ids.csv',index=False,encoding='utf-8',quoting=csv.QUOTE_MINIMAL,lineterminator='\n')
 tops=elig.sort_values('population',ascending=False).head(80)
 # Stratified risk sample: prioritize name/type differences, blank direct admin,
 # and all remaining highest populations; no observations are excluded from the
 # full-vector review above.
 risk=elig[~elig.target_source_record_id.isin(tops.target_source_record_id)].copy()
 risk['risk_score']=(risk.direct_region_cell_status.eq('unknown_not_forwardfilled').astype(int)*4 +
   risk.direct_district_cell_status.eq('unknown_not_forwardfilled').astype(int)*3 +
   risk.legacy_identity_conflict_preserved_not_decided_by_point.fillna(False).astype(bool).astype(int)*5 +
   risk.source_native_id_opaque_not_code.astype(str).ne('').astype(int) + risk.population.astype(float).rank(pct=True))
 risks=risk.sort_values(['risk_score','population'],ascending=False).head(80)
 tops.to_csv(OUT/'top_population_review_sample80.csv',index=False,encoding='utf-8',quoting=csv.QUOTE_MINIMAL,lineterminator='\n')
 risks.to_csv(OUT/'risk_review_sample80.csv',index=False,encoding='utf-8',quoting=csv.QUOTE_MINIMAL,lineterminator='\n')
 receipt={'status':'independent_rural_point_review_complete_candidate_only','candidate_source_receipt_sha256':sha(SRC/'receipt.json'),
   'candidate_point_uses_sha256':sha(POINTS),'frozen_selected_sha256':sha(SELECTED),'classifier_sql_sha256':sha(SQL),'geokladr_dbf_sha256':sha(DBF),
   'counts':{'submitted_point_use_rows':len(p),'unique_selected_census_source_ids':len(selected),'full_vector_raw_classifier_dbf_checked':len(rr),
   'full_vector_selected_census_raw_workbook_checked':len(wb),'eligible_point_only_rows':len(eligible),'failed_raw_review_rows':int((~result).sum()),
   'eligible_by_year':{str(k):int(v) for k,v in eligible.groupby('target_year').size().items()},
   'eligible_current_selected_population_by_year':{str(k):int(v) for k,v in eligible.groupby('target_year').population.sum().items()},
   'selected_workbook_source_hashes_matching_manifest':int(wb.selected_source_file_hash_matches_manifest_and_selected_row.sum()),
   'selected_full_region_name_type_keys_unique':int(wb.selected_full_table_region_name_type_key_unique.sum()),
   'exact_unique_2009_classifier_codes':int(rr.sql_2009_code_unique_in_full_source.sum()),
   'exact_unique_2011_dbf_codes':int(rr.dbf_2011_code_unique_in_full_source.sum()),
   'selected_raw_label_and_population_exact':int((wb.label_matches_selected_candidate & wb.population_matches_selected_candidate).sum()),
   'frozen_source_evidence_region_admin_matches_selected':int(l.frozen_source_evidence_region_admin_matches_selected.sum()),
   'shared_point_collisions_unheld':int(l.shared_same_year_point_hold.sum()),
   'prior_quarantine_unheld':int(l.prior_quarantine.sum()),
   'candidate_temporal_identity_or_modern_continuity_flags_true':int((l.temporal_identity_admitted|l.modern_point_continuity_admitted|l.population_boundary_comparability_asserted|l.census_date_coordinate_claimed).sum()),
   'accepted_temporal_identity_or_population_admissions':0,'eligible_native_id_compared_as_OKATO':0,
   'rows_with_blank_direct_region_cell':int((~wb.direct_region_cell_present).sum()),'rows_with_blank_direct_district_cell':int((~wb.direct_district_cell_present).sum())},
   'raw_review_rule':'Reopened all selected Excel rows at exact sheet/row locator; exact population/name and frozen selected row checks. Reopened every exact 2009 SQL line and 2011 DBF record/byte offset; same exact 11 digit code, literal names normalized, raw DBF coordinate and source version checks.',
   'administrative_context':'Direct raw cells remain unfilled; blank direct region/district is retained as blank/unknown. Selected-region cross-check is retained separately and does not fill a source cell.',
   'interpretation':'Coordinates can be staged as an explicit retrospective named-physical-place representative point based on stable census name/type/region and independent 2009/2011 source match. No exact census-date measurement, temporal identity, OKATO native-ID assertion, current identifier binding, or population-boundary comparability.',
   'files':{},'review_script_sha256':sha(Path(__file__).resolve()),'input_hashes':{str(x):sha(x) for x in [LEDGER,POINTS,SELECTED,SQL,DBF]}}
 for f in sorted(OUT.glob('*')):
  if f.is_file() and f.name!='receipt.json':receipt['files'][f.name]=sha(f)
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(receipt['counts'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
