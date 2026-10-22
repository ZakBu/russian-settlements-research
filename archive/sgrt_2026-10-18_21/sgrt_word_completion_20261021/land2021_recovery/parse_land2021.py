from pathlib import Path
import pandas as pd,re,json,hashlib
O=Path(__file__).resolve().parent;P=Path('/workspace/scratch/sgrt_land2021/rosreestr2021_full_mirror.pdf');T=P.with_suffix('.txt');pages=T.read_text().split('\f');a=json.loads((O/'full_report_acquisition_receipt.json').read_text());rows=[];controls=[]
def clean(s):return re.sub(r'\s+',' ',s).strip()
for pi in range(173,179):
 lines=pages[pi].splitlines()
 for li,line in enumerate(lines):
  m=re.match(r'^\s*(\d{1,2})\s+',line)
  if not m:continue
  tail=line[m.end():];nm=re.search(r'\d+(?:,\d+)?',tail)
  if nm is None:continue
  nums=re.findall(r'\d+(?:,\d+)?',tail[nm.start():]);name=clean(tail[:nm.start()]);code=int(m[1])
  if not name or not re.search('[А-Яа-я]',name):
   before=clean(lines[li-1][15:40]) if li else '';after=clean(lines[li+1][15:40])if li+1<len(lines)else'';name=clean(before+' '+name+' '+after)
  if len(nums)<10 or not re.search('[А-Яа-я]',name):continue
  total,farmland,arable=[float(n.replace(',','.'))for n in nums[:3]]
  rows.append(dict(subject_code_in_Rosreestr_source=f'{code:02}',region_name_raw=name,year=2021,reference_date='2022-01-01',farmland_all_territory_thousand_ha_2021=farmland,farmland_all_territory_ha_2021=farmland*1000,land_total_thousand_ha_2021=total,arable_all_territory_thousand_ha_2021=arable,source_unit='thousand hectares',source_grain='federal_subject_not_municipality',source_definition='actual agricultural land-use classes across ALL statutory land categories: arable,fallow,perennial plantations,hayfields,pasture; not agricultural-designation land category',source_table='Appendix2',source_PDF_page=pi+1,source_printed_page=pi+1,source_layout_line_1based=li+1,source_raw_line=line,source_neighbor_lines_json=json.dumps(lines[max(0,li-1):li+2],ensure_ascii=False),source_sha256=a['sha256'],source_mirror_archive_URL=a['url'],source_original_official_URL='https://rosreestr.gov.ru/upload/Doc/16upr/Государственный (национальный) доклад о состоянии и использовании земель в РФ в 2021 году.pdf',source_local_path=str(P),municipal_boundary_allocation_performed=False))
f=pd.DataFrame(rows);assert len(f)==85 and f.subject_code_in_Rosreestr_source.is_unique;f.to_parquet(O/'regional_farmland2021_primary.parquet',index=False);f.to_csv(O/'regional_farmland2021_primary.csv',index=False)
r=dict(PDF_bytes=P.stat().st_size,PDF_sha256=a['sha256'],source_appendix=2,source_pages_1based=[174,175,176,177,178,179],region_rows=len(f),farmland_region_sum_thousand_ha=float(f.farmland_all_territory_thousand_ha_2021.sum()),farmland_national_source_control_thousand_ha=221907.1,farmland_difference_thousand_ha=float(f.farmland_all_territory_thousand_ha_2021.sum()-221907.1),territory_region_sum_thousand_ha=float(f.land_total_thousand_ha_2021.sum()),territory_national_source_control_thousand_ha=1712519.2,territory_difference_thousand_ha=float(f.land_total_thousand_ha_2021.sum()-1712519.2),date='2022-01-01=end2021',overlapping_parent_regions=False,farmland_not_land_designation_category=True,source_grain='federal_subject');(O/'land_parse_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False,indent=2));print(f[['subject_code_in_Rosreestr_source','region_name_raw','farmland_all_territory_thousand_ha_2021']].to_string(index=False))
