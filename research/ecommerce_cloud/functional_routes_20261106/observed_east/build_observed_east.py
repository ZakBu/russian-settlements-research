#!/usr/bin/env python3
"""Rebuild source-backed eastern search register and fixed-cohort controls.

Raw search responses are retained in ignored work; search engines are not stable
sampling frames. No user origin inferred from pickup address or review profile.
"""
from pathlib import Path
import csv,hashlib,json,re
import pandas as pd
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
WORK=ROOT/'work/ecommerce_functional_routes_20261106/observed_east'
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024'
SYSTEM=BASE/'settlement_role_stage_20261024/system/centre_system_demography.csv'
AXIS=BASE/'national/national_target_source2021.parquet'
OLD=ROOT/'research/ecommerce_cloud/observed_operations_20261104'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,rows):
 assert rows
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,lineterminator='\n',fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def main():
 system=pd.read_csv(SYSTEM);axis=pd.read_parquet(AXIS)
 assert system.source_record_id_2021.is_unique and axis.source_record_id_2021.is_unique
 medium=system[system.medium_primary2002.eq(True)];assert len(medium)==1273
 calls=json.loads((WORK/'search_calls.json').read_text());assert len(calls)==63
 names=set(r['centre'] for r in calls)-{'exploratory'};assert len(names)==30
 selected=medium[medium.name_2021.isin(names)]
 assert len(selected)==30 and set(selected.name_2021)==names
 old_names=set()
 for p in OLD.glob('systematic_review_search*.csv'):
  d=pd.read_csv(p);old_names.update(d['city' if 'city' in d else 'centre'])
 assert not names & old_names
 queryrows=[]
 for r in calls:
  raw=Path(r['path']);assert raw.exists()
  txt=raw.read_text();blocks=txt.split('\n--------------------------------------------------------------------------------\n')
  urls=[]
  for b in blocks:
   for u in re.findall(r'\((https?://[^\n]+)\)',b.split('\n',1)[0]):
    urls.append(u)
  city=r['centre'];record=selected[selected.name_2021.eq(city)]
  q={**r,'search_date_utc':'2026-11-06','phase':'exploration' if city=='exploratory' else 'supplementary_far_east' if city=='Анадырь' else 'planned_ural_siberia_volga','returned_source_blocks_n':len(blocks),'returned_urls_n':len(urls),'returned_urls_json':json.dumps(urls,ensure_ascii=False),'raw_sha256':sha(raw),'screened_scope':'returned titles/snippets; full text only for separately registered sources','screening_result':'no_additional_eligible_named_change_in_screened_results'}
  if city!='exploratory':
   q.update(source_record_id_2021=record.iloc[0].source_record_id_2021,region_2021=record.iloc[0].region_2021,population_2002=int(record.iloc[0].population_2002),medium_primary2002=True)
  if r['id']==31:q['screening_result']='lead_ugolnye_kopi_anadyr_prior_link_and_operating_local_alternative; outside planned geography'
  if r['id']==36:q['screening_result']='abramovo_kuybyshev_work_and_healthcare_link; not platform-caused change'
  if r['id']==63:q['screening_result']='reproduces source_ugolnye_kopi_anadyr; same independent source'
  q['path']=str(raw.relative_to(ROOT));queryrows.append(q)
 # Initial reconnaissance is separately declared: exact queries retained, response
 # lives in conversation, not falsely represented as a locally archived response.
 prerecon=[('exploratory','"Озон" "ездить" "райцентр" "Сибирь"'),('exploratory','"пункт выдачи" "раньше ездили" Урал'),('exploratory','"маркетплейсы" "раньше ездили" Татарстан'),('Талица','"Ozon" "ездить в" "Талицу"'),('Ирбит','"Wildberries" "ездить в" "Ирбит"'),('Ялуторовск','"Озон" "ездить в" "Ялуторовск"'),('Камышлов','"пункт" "раньше" "в Камышлов" отзывы'),('Урень','"пункт выдачи" "в Урень" "ездить"')]
 for n,(city,q) in enumerate(prerecon,1):
  queryrows.append({'id':f'R{n:02}','centre':city,'q':q,'path':'conversation_only','phase':'initial_reconnaissance_not_part_of_archived_30_centre_frame','search_date_utc':'2026-11-06','screened_scope':'returned snippets in conversation; response not retained locally','screening_result':'no accepted case from this call'})
 write('query_log.csv',queryrows)
 cohort=[]
 for r in selected.itertuples():
  rr=[q for q in queryrows if isinstance(q['id'],int) and q['centre']==r.name_2021]
  cohort.append({'centre':r.name_2021,'region_2021':r.region_2021,'source_record_id_2021':r.source_record_id_2021,'population_2002':int(r.population_2002),'medium_primary2002':True,'in_previous_24_centre_search':False,'archived_queries_n':len(rr),'scope':'supplementary_far_east_from_broad_search' if r.name_2021=='Анадырь' else 'planned_ural_siberia_volga','strict_observed_trip_reduction_cases_n':0,'named_prior_link_operating_local_alternative_sources_n':int(r.name_2021=='Анадырь'),'retained_nonshopping_route_sources_n':int(r.name_2021=='Куйбышев')})
 assert all(r['archived_queries_n']==2 for r in cohort if r['centre']!='Анадырь')
 write('cohort_filter.csv',cohort)
 links=[]
 for name,reg,typ,district in [('Угольные Копи','чукотский','пгт','Анадырский'),('Анадырь','чукотский','город',''),('Абрамово','новосибирская','село','Куйбышевский'),('Куйбышев','новосибирская','город','')]:
  d=axis[axis.name_2021.eq(name)&axis.region_2021.eq(reg)&axis.type_2021.eq(typ)]
  if district:d=d[d.district_2021.str.contains(district,regex=False)]
  assert len(d)==1
  r=d.iloc[0];links.append({'name':name,'region_2021':reg,'type_2021':typ,'district_2021':r.district_2021,'source_record_id_2021':r.source_record_id_2021,'population_2002':r.population_2002,'population_2021':r.population_2021,'fixed_medium_centre':r.source_record_id_2021 in set(medium.source_record_id_2021),'source_name_context':'settlement name and district explicit in article; no closest-point assignment'})
 write('named_place_links.csv',links)
 pins={'system':{'path':str(SYSTEM.relative_to(ROOT)),'sha256':sha(SYSTEM)},'axis':{'path':str(AXIS.relative_to(ROOT)),'sha256':sha(AXIS)},'archived_search_calls_n':63,'initial_reconnaissance_not_archived_n':8,'total_declared_queries_n':71,'planned_new_centres_n':29,'supplementary_far_east_centres_n':1,'old_centres_overlap_n':0,'strict_measured_or_self_reported_trip_reduction_cases_in_planned_region_n':0,'named_prior_link_and_working_local_alternative_sources_n':1,'independent_nonshopping_route_sources_n':1,'query_response_sha256_pinned_in_csv':True,'scope_is_not_probability_sample':True}
 (OUT/'search_and_cohort_summary.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(pins,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
