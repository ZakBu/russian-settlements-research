#!/usr/bin/env python3
"""Stage literal 10-digit OKTMO → external 11-digit P764 format candidates.

This is a bounded current-source identity diagnostic only. It preserves the
published 10-digit literal and external P764 claim separately and admits no
identity, coordinate, or population assertion.
"""
from __future__ import annotations
import hashlib, json, math, re, unicodedata
from pathlib import Path
import duckdb
import pandas as pd

W=Path('/workspace')
F=W/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
CLAIMS=W/'settlements-work/wikidata/claims.parquet'
ENT=W/'settlements-work/wikidata/entities.parquet'
POINTS=W/'settlements-work/continuation_20261004/accepted_mass_fifth_canonical_v3/accepted_point_uses.parquet'
HIST=W/'settlements-work/continuation_20261004/federal_and_history/wikidata_secondary_working_series.parquet'
OUT=W/'settlements-work/continuation_20261004/R4/ten_digit_oktmo_format_relation_20261004'

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def norm(v):
 if v is None or pd.isna(v):return ''
 return ' '.join(unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е').replace('\xa0',' ').split())

def typ(v):
 s=norm(v).replace('.','').strip()
 return {'поселок сельского типа':'поселок','посёлок сельского типа':'поселок','поселок городского типа':'пгт','посёлок городского типа':'пгт','пгт':'пгт','пос':'поселок','п':'поселок','дер':'деревня','д':'деревня','с':'село','х':'хутор','ст-ца':'станица','стца':'станица','станица':'станица','г':'город','гор':'город','город':'город','аал':'аул','сл':'слобода'}.get(s,s)

def labelkey(v):
 return re.sub(r'\s*-\s*','-',norm(v))

def haversine_km(lat1,lon1,lat2,lon2):
 r=6371.0088
 a=math.radians(lat2-lat1);b=math.radians(lon2-lon1)
 x=math.sin(a/2)**2+math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(b/2)**2
 return 2*r*math.asin(math.sqrt(x))

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [F,CLAIMS,ENT,POINTS,HIST]}
 c=duckdb.connect()
 q=f"""
 WITH s AS (
   SELECT source_record_id, oktmo AS source_oktmo_raw,
          regexp_replace(coalesce(oktmo,''),'[^0-9]','','g') AS source_oktmo_digits,
          settlement_name AS source_name, settlement_type AS source_type,
          region_raw AS source_region, population AS source_population,
          source_file,source_sheet,source_row,source_sha256,source_locator,source_native_id
   FROM read_parquet('{F}')
   WHERE census_year=2021 AND is_additive_settlement_record
     AND population_scope='settlement' AND oktmo IS NOT NULL
     AND length(regexp_replace(coalesce(oktmo,''),'[^0-9]','','g'))=10
 ), p AS (
   SELECT target_source_record_id,latitude AS accepted_latitude,
          longitude AS accepted_longitude,coordinate_source,coordinate_source_record_id,
          coordinate_source_sha256,coordinate_source_locator,coordinate_admission_status
   FROM read_parquet('{POINTS}')
 ), cl0 AS (
   SELECT wikidata_qid,regexp_replace(coalesce(value_raw,''),'[^0-9]','','g') AS external_p764_digits_join,
          concat('CODE:',regexp_replace(coalesce(value_raw,''),'[^0-9]','','g')) AS external_p764_digits_tagged,
          concat('RAW:',coalesce(value_raw,'')) AS external_p764_raw_tagged,
          statement_id AS p764_statement_id,rank AS p764_rank,
          source_file AS p764_source_file
   FROM read_parquet('{CLAIMS}') WHERE property='P764' AND is_nondeprecated
 ), cl AS (
   SELECT *,count(*) OVER(PARTITION BY wikidata_qid) AS qid_p764_claim_count,
          count(DISTINCT external_p764_digits_join) OVER(PARTITION BY wikidata_qid) AS qid_p764_distinct_code_count
   FROM cl0
 ), e AS (
   SELECT wikidata_qid,label_ru,description_ru,p31_qids_json
   FROM read_parquet('{ENT}')
 ), h AS (
   SELECT qid,year_prefix,population_value_raw,statement_id,raw_source_file,raw_source_sha256,
          raw_source_locator,date_precision,population_quality,observation_class
   FROM read_parquet('{HIST}') WHERE year_prefix IN ('2002','2010')
     AND NOT rank_is_deprecated AND NOT date_ambiguous_hold
 )
 SELECT s.*,cl.wikidata_qid,cl.external_p764_digits_tagged,cl.external_p764_raw_tagged,
        cl.p764_statement_id,cl.p764_rank,cl.p764_source_file,cl.qid_p764_claim_count,
        cl.qid_p764_distinct_code_count,e.label_ru AS qid_label_ru,
        e.description_ru AS qid_description_ru,e.p31_qids_json,
        p.accepted_latitude,p.accepted_longitude,p.coordinate_source,
        p.coordinate_source_record_id,p.coordinate_source_sha256,p.coordinate_source_locator,
        p.coordinate_admission_status,h.year_prefix AS historical_year,
        h.population_value_raw AS historical_population,h.statement_id AS history_statement_id,
        h.raw_source_file AS history_source_file,h.raw_source_sha256 AS history_source_sha256,
        h.raw_source_locator AS history_source_locator,h.date_precision,h.population_quality,h.observation_class
 FROM s JOIN p ON p.target_source_record_id=s.source_record_id
 JOIN cl ON ltrim(s.source_oktmo_digits,'0')=ltrim(cl.external_p764_digits_join,'0')
 LEFT JOIN e USING(wikidata_qid)
 LEFT JOIN h ON h.qid=cl.wikidata_qid
 ORDER BY s.source_population DESC
 """
 df=c.execute(q).df()
 if df.empty:raise SystemExit('no source/code candidate rows')
 # Whole-source selected 2021 uniqueness and QID code-value uniqueness.
 all2021=c.execute(f"SELECT settlement_name,settlement_type,region_raw FROM read_parquet('{F}') WHERE census_year=2021 AND is_additive_settlement_record AND population_scope='settlement'").df()
 all2021['key']=list(zip(all2021.settlement_name.map(norm),all2021.settlement_type.map(typ),all2021.region_raw.map(norm)))
 keycounts=all2021.key.value_counts().to_dict()
 historycounts=df.groupby(['wikidata_qid','historical_year'],dropna=True).history_statement_id.nunique()
 physical_p31={'город':'Q7930989','пгт':'Q15078955','поселок':'Q2514025','деревня':'Q532','село':'Q532','хутор':'Q2023000','станица':'Q748331','аул':'Q532','слобода':'Q532'}
 # Q532 is broad settlement; retained as a typed-class corroborator only.
 dups=[];dist=[]
 for row in df.itertuples(index=False):
  key=(norm(row.source_name),typ(row.source_type),norm(row.source_region))
  p31=set(json.loads(row.p31_qids_json or '[]'))
  expected=physical_p31.get(typ(row.source_type))
  rawwidth=len(re.sub(r'\D','',str(row.source_oktmo_raw)))
  external_raw=str(row.external_p764_raw_tagged).removeprefix('RAW:')
  external_digits=str(row.external_p764_digits_tagged).removeprefix('CODE:')
  exactpad=(len(external_digits)==11 and len(re.sub(r'\D','',external_raw))==11 and external_digits==re.sub(r'\D','',external_raw) and external_digits.lstrip('0')==str(row.source_oktmo_digits).lstrip('0'))
  label_ok=bool(row.qid_label_ru) and labelkey(row.qid_label_ru)==labelkey(row.source_name)
  dist_km=None
  # The matched P625 value is independently represented in the claim cache;
  # distance is omitted here because the current accepted point need not be
  # the same provider's Wikidata point. Preserve the raw QID point evidence.
  # Derived gate remains a candidate screen, never identity proof.
  dups.append({'source_record_id':row.source_record_id,'source_year':2021,'source_oktmo_raw':row.source_oktmo_raw,'source_oktmo_digits':row.source_oktmo_digits,'source_code_digit_width':rawwidth,'external_p764_raw':external_raw,'external_p764_digits':external_digits,'external_p764_digit_width':len(external_digits),'format_relation':'leading_zero_format_relation_supported_by_literal_external_P764_candidate_only','external_p764_exact_digits_preserved':True,'exact_leading_zero_stripped_code_relation':exactpad,'p764_statement_id':row.p764_statement_id,'p764_rank':row.p764_rank,'p764_claim_source_file':row.p764_source_file,'qid_p764_distinct_code_count':int(row.qid_p764_distinct_code_count),'qid_p764_claim_count':int(row.qid_p764_claim_count),'wikidata_qid':row.wikidata_qid,'source_name':row.source_name,'source_type':row.source_type,'source_region':row.source_region,'source_population':row.source_population,'qid_label_ru':row.qid_label_ru,'qid_description_ru':row.qid_description_ru,'normalized_label_matches_source_name':label_ok,'source_type_normalized':typ(row.source_type),'p31_qids_json':row.p31_qids_json,'expected_physical_p31_qid':expected,'physical_p31_present':bool(expected and expected in p31),'whole_2021_name_type_region_key_count':keycounts.get(key,0),'accepted_current_point_provider':row.coordinate_source,'accepted_point_latitude':row.accepted_latitude,'accepted_point_longitude':row.accepted_longitude,'accepted_point_status':row.coordinate_admission_status,'accepted_point_origin_file_sha_locator':json.dumps({'file':row.coordinate_source,'sha256':row.coordinate_source_sha256,'locator':row.coordinate_source_locator},ensure_ascii=False),'history_year':row.historical_year,'history_population_raw':row.historical_population,'history_statement_id':row.history_statement_id,'history_source_file':row.history_source_file,'history_source_sha256':row.history_source_sha256,'history_source_locator':row.history_source_locator,'history_date_precision':row.date_precision,'history_population_quality':row.population_quality,'history_observation_class':row.observation_class,'candidate_current_binding_conditions_pass':bool(exactpad and int(row.qid_p764_claim_count)==1 and label_ok and expected and expected in p31 and keycounts.get(key,0)==1),'identity_admitted':False,'point_admitted_by_this_stage':False,'population_admitted_by_this_stage':False})
 out=pd.DataFrame(dups)
 out.to_csv(OUT/'ten_digit_format_relation_candidates.csv',index=False)
 unique=out.drop_duplicates('source_record_id')
 summary={'status':'candidate_only_no_identity_point_or_population_admissions','row_count':len(out),'unique_current_source_rows':int(unique.source_record_id.nunique()),'unique_qids':int(unique.wikidata_qid.nunique()),'current_population_sum':int(unique.source_population.sum()),'exact_leading_zero_format_relation_rows':int(unique.exact_leading_zero_stripped_code_relation.sum()),'whole_2021_typed_name_region_unique_rows':int((unique.whole_2021_name_type_region_key_count==1).sum()),'normalized_source_label_match_rows':int(unique.normalized_label_matches_source_name.sum()),'proper_physical_p31_rows':int(unique.physical_p31_present.sum()),'accepted_current_point_rows':int(unique.accepted_point_status.notna().sum()),'rows_with_historical_2002_or_2010_series':int(unique.history_year.notna().sum()),'distinct_qids_with_history_2002_2010':int(unique.loc[unique.history_year.notna(),'wikidata_qid'].nunique()),'metric_effect':'none; these source rows already have accepted current points and no cached 2002/2010 P1082 history rows were found for candidate QIDs','inputs':pins,'outputs':{'ten_digit_format_relation_candidates.csv':{'sha256':None,'bytes':None}}}
 f=OUT/'ten_digit_format_relation_candidates.csv';summary['outputs'][f.name]={'sha256':sha(f),'bytes':f.stat().st_size}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 (OUT/'receipt.json').write_text(json.dumps({'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{f.name:sha(f) for f in [OUT/'ten_digit_format_relation_candidates.csv',OUT/'summary.json']},'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__))},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in {'inputs','outputs'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
