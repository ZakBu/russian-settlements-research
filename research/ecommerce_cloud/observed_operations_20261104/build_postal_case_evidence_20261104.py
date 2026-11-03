#!/usr/bin/env python3
"""Save three manually adjudicated 2023 geography cases plus a rejected candidate.

All source row references are to a fixed historical PDF. They do not establish
2022 continuity or operating pickup points. Case assertions require reading the
cited primary documents; this script only reproduces the selected registry.
"""
import argparse,csv,hashlib,json
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
WORK=ROOT/'work/ecommerce_operations_20261104'
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--base',type=Path,default=ROOT/'work/sources/research/ecommerce_settlement_20261024/national/national_target_source2021.parquet')
 parser.add_argument('--sources',type=Path,default=WORK/'sources')
 args=parser.parse_args();basepath=args.base
 registry=json.loads((HERE/'postal_case_sources.json').read_text())
 pin=next(r for r in registry['inputs'] if r['path'].endswith('national_target_source2021.parquet'))
 assert hashlib.sha256(basepath.read_bytes()).hexdigest()==pin['sha256']
 for r in registry['independent_address_sources']:
  assert hashlib.sha256((args.sources/Path(r['raw_file']).name).read_bytes()).hexdigest()==r['sha256']
 base=pd.read_parquet(basepath)
 with (WORK/'ozon_tariff_geography2023_all.csv').open() as f:geo={int(r['row2023_n']):r for r in csv.DictReader(f)}
 definitions=[
  (1235,8596,'нижегородская','станции Тарасиха','посёлок','supported_2023_geographic_identity','nn_ministry_social_registry2020','PDF page67, registry1637','Type поселок plus postal606630 and independent official address поселок станции Тарасиха support this candidate. The 2022 short name remains unadjudicated.'),
  (1235,8596,'нижегородская','Тарасиха','деревня','rejected_for_this_2023_record','nn_ministry_social_registry2020','PDF page67, registry1637','Exact bare-name village contradicts the explicit settlement type in the 2023 source. Population2 is not a policy-threshold counterexample.'),
  (2164,20385,'тверская','"Чуприяновка"','железнодорожный объект','supported_2023_geographic_identity','kalinin_services_2017','PDF pages10–11','Ozon explicitly names железнодорожная станция with postal170536. Municipal decree names the same type, postal and Kalininsky district; quotation marks in census name do not name another location.'),
  (2165,20333,'тверская','Квакшино','деревня','supported_2023_geographic_identity','kalinin_services_2017','PDF page4','Ozon village+postal170555 agrees with independent municipal addresses for village Kvakshino in Kalininsky district.')]
 rows=[]
 for oldid,gid,reg,name,typ,status,source,locator,note in definitions:
  g=geo[gid];cand=base.loc[base.region_2021.eq(reg)&base.name_2021.eq(name)&base.type_2021.eq(typ)]
  assert len(cand)==1
  q=cand.iloc[0]
  rows.append({'row2022_name_reference':oldid,'row2023_n':gid,'page2023':g['pdf_page'],'region2023':g['region2023'],'name2023':g['name2023'],'postal_index2023':g['postal_index2023'],'census2021_source_record_id':q.source_record_id_2021,'census2021_name':q.name_2021,'census2021_type':q.type_2021,'census2021_district':q.district_2021,'census2021_population':int(q.population_2021),'assessment_for_2023_only':status,'independent_source_id':source,'independent_source_locator':locator,'basis':note,'identity2022_confirmed':False,'pickup_operation_confirmed':False})
 with (HERE/'postal_identity_case_evidence.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 print('Saved 3 supported 2023 geographic identities and 1 rejected candidate; 0 inferred 2022 identities or pickup operations.')
if __name__=='__main__':main()
