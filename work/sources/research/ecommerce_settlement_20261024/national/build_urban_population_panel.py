# coding: utf-8
"""Conservative name/type/region linkage only. No TERSON->OKTMO guesses or causal model."""
from pathlib import Path
import csv,json,re,hashlib
from collections import defaultdict,Counter
import pyarrow as pa
import pyarrow.parquet as pq
P=Path(__file__).resolve().parent
BASE=P/'national_target_source2021.parquet'

def text_norm(s):
 return re.sub(r'[^а-яa-z0-9]+',' ',str(s or '').lower().replace('ё','е')).strip()

def region_norm(s):
 s=str(s or '').lower().replace('ё','е')
 s=re.split(r',?\s+(?:включая|без учета|без автоном|в том числе)',s)[0]
 s=s.replace('кемеровская область - кузбасс','кемеровская область')
 s=re.sub(r'\([^)]*(?:автоном|кроме)[^)]*\)','',s)
 s=re.sub(r'\b(?:республика|область|край|автономный|автономная|округ)\b',' ',s)
 return text_norm(s)

def writecsv(path,rows):
 if not rows:path.write_text('',encoding='utf-8');return
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

base=pq.read_table(BASE).to_pylist()
urban=[r for r in base if r['type_2021'] in ('город','пгт')]
keys=defaultdict(list)
for r in urban:keys[(region_norm(r['region_2021']),text_norm(r['name_2021']),r['type_2021'])].append(r)
# A key must also be unique in the full physical inventory, including not-credited alternatives.
inv=pq.read_table(P/'all_physical_source2021_inventory.parquet').to_pylist();allkeys=Counter((region_norm(r['region_2021']),text_norm(r['name_2021']),r['type_2021']) for r in inv if r['type_2021'] in ('город','пгт'))
links=[];review=[];peryear={}
for year in (2022,2023,2024,2025):
 with (P/f'rosstat_urban_np_candidates_{year}.csv').open(encoding='utf-8-sig') as f:rr=list(csv.DictReader(f))
 skeys=defaultdict(list)
 for r in rr:
  typ='город' if r['type_raw']=='г' else 'пгт'
  source_name=re.sub(r'\s+(?:рп|пгт|кп|дп)$','',r['name_without_type'],flags=re.I) if typ=='пгт' else r['name_without_type']
  k=(region_norm(r['region']),text_norm(source_name),typ)
  skeys[k].append(r)
 counts=Counter()
 for k,group in skeys.items():
  targets=keys.get(k,[])
  if len(group)!=1:status='ambiguous_source_key'
  elif len(targets)>1:status='ambiguous_target_key'
  elif len(targets)==1 and allkeys[k]!=1:status='ambiguous_all_physical_inventory_key'
  elif len(targets)==0:status='no_compatible_unique_target'
  else:status='matched_unique_region_name_compatible_type'
  counts[status]+=len(group)
  for src in group:
   audit={'year':year,'region_raw':src['region'],'region_normalized':k[0],'name_raw':src['name_raw'],'type_compatible':k[2],'source_excel_row':int(src['source_excel_row']),'source_sheet':src['sheet'],'source_filename':src['source_filename'],'source_territory_code_raw':src['source_territory_code_raw'],'target_candidates_n':len(targets),'source_key_rows_n':len(group),'all_physical_key_rows_n':allkeys[k],'link_status':status}
   if not status.startswith('matched'):review.append(audit);continue
   tar=targets[0]
   row={**audit,'root_accepted20261022':tar['root_accepted20261022'],'source_record_id_2021':tar['source_record_id_2021'],'name_2021':tar['name_2021'],'type_2021':tar['type_2021'],'region_2021':tar['region_2021'],'district_2021':tar['district_2021'],'population_2021':tar['population_2021'],'population_persons':int(float(src['population_persons'])),'observation_date':src['reference_date'],'source_url':src['source_url'],'unit':'persons','population_scope':'own_named_urban_settlement_candidate','boundary_comparability':'unknown_not_independently_verified','census_base_2022_2023_comparability':'incompatible_vintages_do_not_compute_2022_2023_growth','WB_focus20261021_count':tar['WB_focus20261021_count'],'WB_evidence_status':tar['WB_evidence_status'],'WB_evidence_status_sensitivity':tar['WB_evidence_status_sensitivity'],'historical_exposure_status':'unknown_no_opening_date','causal_interpretation':'not_identified'}
   links.append(row)
 peryear[str(year)]=dict(counts)
assert len({(r['source_record_id_2021'],r['year']) for r in links})==len(links)
assert len({(r['source_filename'],r['source_sheet'],r['source_excel_row']) for r in links})==len(links)
wide=[];byid=defaultdict(dict)
for r in links:byid[r['source_record_id_2021']][r['year']]=r
for tar in urban:
 vals=byid.get(tar['source_record_id_2021'],{})
 r={**tar,'urban_post2021_link_method':'unique normalized region+name+compatible type; also unique in full physical inventory','boundary_comparability':'unknown_not_independently_verified','complete_2023_2025':all(y in vals for y in (2023,2024,2025)),'population_2022_2023_growth_permitted':False,'causal_interpretation':'not_identified'}
 for year in (2022,2023,2024,2025):
  src=vals.get(year)
  r[f'population_{year}']=src['population_persons'] if src else None
  r[f'link_status_{year}']='matched_unique_region_name_compatible_type' if src else 'unknown_no_conservative_unique_link'
  for col in ('source_excel_row','source_sheet','source_filename','source_url','source_territory_code_raw','observation_date'):
   r[f'{col}_{year}']=src[col] if src else None
 wide.append(r)
pq.write_table(pa.Table.from_pylist(links),P/'urban_population_panel_linked_long.parquet',compression='zstd')
pq.write_table(pa.Table.from_pylist(wide),P/'urban_population_panel_main_wide.parquet',compression='zstd')
writecsv(P/'urban_population_linkage_review.csv',review)
# Compact review-friendly CSV includes population columns and source locators, no WB duplication.
compact=[{k:r[k] for k in ['root_accepted20261022','source_record_id_2021','name_2021','type_2021','region_2021','district_2021','population_2021','population_2022','population_2023','population_2024','population_2025','complete_2023_2025','boundary_comparability']} for r in wide]
writecsv(P/'urban_population_panel_main_compact.csv',compact)
summary={'checked_on':'2026-10-24','base_input':str(BASE),'base_sha256':hashlib.sha256(BASE.read_bytes()).hexdigest(),'accepted_working_target_rows':len(base),'accepted_working_urban_city_pgt_rows':len(urban),'all_physical_city_pgt_rows':sum(r['type_2021'] in ('город','пгт') for r in inv),'all_target_urban_preserved_in_wide':len(wide),'linked_year_records':len(links),'linked_counts_by_year':dict(Counter(r['year'] for r in links)),'complete_2023_2025_rows':sum(r['complete_2023_2025'] for r in wide),'all_four_post_years_rows':sum(all(r[f'population_{y}'] is not None for y in (2022,2023,2024,2025)) for r in wide),'review_records':len(review),'peryear_status':peryear,'join_rule':'Unique normalized region+settlement name+compatible type (г=город,пгт/рп/urban-п=пгт); redundant terminal рп/пгт/кп/дп markers removed for pgt names. Also unique across all physical source2021 inventory. No TERSON/OKTMO guess, no municipal population transfer, no duplicate aggregation.','unknown_rule':'Unlinked urban targets remain in wide with null population and explicit unknown status. Rural target unchanged in authoritative base.','comparability':'Identity linkage only; boundary identity across dates is unknown.2022pre-census vs2023post-census break preserved; no2022–2023growth. Census2021 vsJan2023different reference dates.','not_done':['No causal regression','No population-growth attribution to current WB/Ozon','No general claim that date of first source appearance is an opening date','No assumption all source urban candidate rows are unique own settlements; federal-city internal units excluded by accepted target matching'],'verification':{'unique_target_year':True,'unique_source_row_link':True,'all_target_urban_rows_retained':len(wide)==len(urban),'source_2022_2023_growth_prohibited':True}}
(P/'urban_population_panel_verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
