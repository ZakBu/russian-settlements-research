#!/usr/bin/env python3
"""Full Table5 primary2010 literal-NP/sourceaggregate inventory, no population-based identity."""
from pathlib import Path
import re,json,hashlib,datetime
import pandas as pd
B=Path(__file__).resolve().parent;SRC=B/'sources/national2010_official_volume1_exact.pdf';TEXT=B/'sources/national2010_official_volume1_layout.txt';AX=B.parent/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):
 x=str(x).casefold().replace('ѐ','е').replace('ё','е');x=re.sub(r'[^\w\s]',' ',x);return re.sub(r'\s+',' ',x).strip()
def regionkey(x):
 x=norm(x);x=re.sub(r'\b(республика|область|край|автономный|автономная|округ|г)\b',' ',x);return re.sub(r'\s+',' ',x).strip()
def parentkey(x):
 x=norm(x);x=re.sub(r'\b(муниципальный|муниципальная|район|района|городской|городского|округ|округа|г)\b',' ',x);return re.sub(r'\s+',' ',x).strip()
source_hash=sha(SRC);text=TEXT.read_text();pages=text.split('\f');first=next(i for i,p in enumerate(pages)if '5. ЧИСЛЕННОСТЬ НАСЕЛЕНИЯ РОССИИ' in p);last=next(i for i,p in enumerate(pages[first+1:],first+1)if '6. ГРУППИРОВКА ГОРОДСКИХ' in p)
rx=re.compile(r'\s{2,}(-|[0-9]+)\s+(-|[0-9]+)\s+(-|[0-9]+)\s+(-|[0-9]+,[0-9]+)\s+(-|[0-9]+,[0-9]+)\s*$');rows=[];pending=[];other=[]
for pi in range(first,last):
 for li,line in enumerate(pages[pi].splitlines(),1):
  m=rx.search(line)
  if m:
   label=' '.join(pending+[line[:m.start()].strip()]);locs=[z['line']for z in other[-len(pending):]]if pending else [];pending=[];rows.append({'source_row_id':f'T5:pdfpage{pi+1}:layoutline{li}','source_table':5,'source_pdf_page':pi+1,'source_layout_line':li,'source_label_raw':label,'source_raw_line':line,'source_total_cell_raw':m[1],'source_male_cell_raw':m[2],'source_female_cell_raw':m[3],'source_male_pct_raw':m[4],'source_female_pct_raw':m[5]});continue
  z=line.strip()
  if not z:continue
  if any(k in z for k in ['Продолжение таблицы','В общей численности','населения, процентов','Мужчины','и женщины','мужчины','женщины','Численность и размещение населения','Итоги Всероссийской','5. ЧИСЛЕННОСТЬ','СУБЪЕКТОВ РОССИЙСКОЙ','СЕЛЬСКИХ НАСЕЛЕННЫХ','С НАСЕЛЕНИЕМ 3']):continue
  if z[0].isdigit()or'————'in z:continue
  pending.append(z);other.append({'page_pdf':pi+1,'line':li,'raw_line':line})
a=pd.read_parquet(AX);native=a[a.source_record_id_2010.notna()].copy();regions={regionkey(r):r for r in a.region.dropna().unique()};region=None;parent=None;section=None;classified=[]
typed=re.compile(r'^(?:Городское население\s*-\s*)?(г\.|пгт|село|пос[еѐё]лок|деревня|станица|аул|хутор|насел[еѐё]нный пункт|железнодорожная станция|станция)\s*(.+)$',re.I);typemap={'г.':'город','пгт':'пгт','село':'село','посѐлок':'посёлок','поселок':'посёлок','посёлок':'посёлок','деревня':'деревня','станица':'станица','аул':'аул','хутор':'хутор','населѐнный пункт':'населённый пункт','населенный пункт':'населённый пункт','населённый пункт':'населённый пункт','железнодорожная станция':'железнодорожная станция','станция':'станция'}
for row in rows:
 label=row['source_label_raw'];rk=regionkey(label);row.update(source_region_raw=region,source_region_axis_key=None,source_native2010_parent_raw=parent,source_row_grain='aggregate_or_unresolved',settlement_name_raw=None,settlement_type_raw=None)
 if rk in regions and ('область'in label.lower()or'край'in label.lower()or'республика'in label.lower()or'автономный'in label.lower()):region=label;parent=None;section=None;row['source_row_grain']='region_aggregate'
 elif label in ['г. Москва - городское население','г. Санкт-Петербург - городское население']:region=label.split(' - ')[0];parent=None;section='urban_explicit';row['source_row_grain']='federalcity_region_urban_aggregate_not_auto_owncity'
 elif 'федеральный округ'in label:region=None;parent=None;section=None;row['source_row_grain']='federal_district_aggregate'
 elif 'внутригородск'in label.lower():row['source_row_grain']='intracity_subdivision_aggregate'
 elif 'район'in label.lower()or'подчиненн'in label.lower()or'подчинённ'in label.lower():
  parent=re.sub(r'\s*-\s*сельское население$','',label,flags=re.I);section='rural_explicit' if '- сельское население'in label.lower()else None;row['source_row_grain']='native2010_parent_aggregate'
 elif (m:=typed.match(label))and not any(z in label.lower()for z in ['с подчин','населенными пунктами','населѐнными пунктами','- сельское население','- городское население']):
  row['source_row_grain']='literal_settlement';
  if len(row['source_raw_line'])-len(row['source_raw_line'].lstrip())<=1:parent=None;section=None
  if label.startswith('Городское население - '):section='urban_explicit'
  row['settlement_type_raw']=typemap[m[1].lower()];
  if row['settlement_type_raw']=='город'and section=='rural_explicit':section=None
  row['settlement_name_raw']=re.sub(r'\s*\((?:рц|цмр|цмо)\)\s*$', '',m[2],flags=re.I).strip()
 if label=='Городское население':section='urban_explicit' if parent is not None else None
 if label=='Сельское население':section='rural_explicit' if parent is not None else None
 row['source_statistical_population_section_explicit']=section;row['source_population_section_is_not_inferred_from_legal_type']=True
 row['source_region_raw']=region;row['source_region_axis_key']=regions.get(regionkey(region));row['source_native2010_parent_raw']=parent
 row['population2010_primary_numeric_cell']=int(row['source_total_cell_raw'])if row['source_total_cell_raw'].isdigit()else None;row['male2010_primary_numeric_cell']=int(row['source_male_cell_raw'])if row['source_male_cell_raw'].isdigit()else None;row['female2010_primary_numeric_cell']=int(row['source_female_cell_raw'])if row['source_female_cell_raw'].isdigit()else None;row['source_date']='2010-10-14';row['source_pdf_sha256']=source_hash;row['source_pdf_url']='https://static.statmuseum.ru/results/2010/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf';row['numeric_cell_is_not_population_interval']=True;classified.append(row)
d=pd.DataFrame(classified);literal=d[d.source_row_grain.eq('literal_settlement')].copy();literal['name_key']=literal.settlement_name_raw.map(norm);literal['type_key']=literal.settlement_type_raw.map(norm);literal['parent_key']=literal.source_native2010_parent_raw.fillna('').map(parentkey);native['name_key']=native.name.map(norm);native['type_key']=native.type.map(norm);native['parent_key']=native.district_raw_2010.fillna('').map(parentkey)
sourcefreq=literal.groupby(['source_region_axis_key','type_key','name_key'],dropna=False).size();targetgroups={k:g for k,g in native.groupby(['region','type_key','name_key'],dropna=False)};links=[]
for row in literal.to_dict('records'):
 key=(row['source_region_axis_key'],row['type_key'],row['name_key']);cand=targetgroups.get(key,native.iloc[:0]);status='unmatched_literal_region_type_name';uid=None
 if len(cand)==1 and sourcefreq.get(key,0)==1:uid=cand.iloc[0].id;status='unique_literal_2010_region_type_name_in_both_source_and_native_axis_inventories'
 elif len(cand)>0:
  src=literal[(literal.source_region_axis_key.eq(key[0]))&literal.type_key.eq(key[1])&literal.name_key.eq(key[2])&literal.parent_key.eq(row['parent_key'])];cc=cand[cand.parent_key.eq(row['parent_key'])]
  if row['parent_key']and len(src)==1 and len(cc)==1:uid=cc.iloc[0].id;status='unique_literal_native2010_region_type_name_parent_in_both_sources'
  else:status='ambiguous_literal_identity_requires_native2010_parent'
 row.update(strict_uid=uid,link_status=status,link_identity_uses_population=False,candidate_uids_json=json.dumps(cand.id.tolist(),ensure_ascii=False),source_is_partial_rural_inventory=True,target_original_population2010=None,target_original_quality2010=None,target_native2010_parent_raw=None,target_source_record_id_2010=None)
 if uid:
  z=cand[cand.id.eq(uid)].iloc[0];row.update(target_original_population2010=z.population_2010,target_original_quality2010=z.population_value_quality_2010,target_native2010_parent_raw=z.district_raw_2010,target_source_record_id_2010=z.source_record_id_2010)
 links.append(row)
l=pd.DataFrame(links);l['eligible_numeric_recovery']=l.strict_uid.notna()&l.population2010_primary_numeric_cell.notna();l['proposed_primary2010_count']=l.population2010_primary_numeric_cell.where(l.eligible_numeric_recovery);l['requires_independent_source_and_identity_review_before_axis_change']=True
d.to_parquet(B/'national_table5_all_source_rows.parquet',index=False);literal.to_parquet(B/'national_table5_literal_NP_inventory.parquet',index=False);l.to_parquet(B/'national_table5_full_identity_and_recovery_candidates.parquet',index=False);l[l.eligible_numeric_recovery].to_parquet(B/'national_table5_numeric_strict_review_candidates.parquet',index=False);d[d.source_row_grain.ne('literal_settlement')].to_parquet(B/'national_table5_aggregate_and_unresolved_rows.parquet',index=False);(B/'national_table5_unparsed_text_lines.json').write_text(json.dumps(other,ensure_ascii=False,indent=2))
controls=l[l.settlement_name_raw.isin(['Ипатово','Ровеньки','Псебай','Инта'])];controls.to_csv(B/'national_table5_predeclared_name_controls.csv',index=False);allnum=d[['population2010_primary_numeric_cell','male2010_primary_numeric_cell','female2010_primary_numeric_cell']].notna().all(axis=1);validsum=(d.loc[allnum,'population2010_primary_numeric_cell']==d.loc[allnum,'male2010_primary_numeric_cell']+d.loc[allnum,'female2010_primary_numeric_cell']).all()
r={'status':'ACTUAL_FULL_TABLE5_SOURCE_EXTRACTION_AND_IDENTITY_CANDIDATES_PENDING_INDEPENDENT_REVIEW','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_pdf_sha256':sha(SRC),'source_text_sha256':sha(TEXT),'source_axis_sha256':sha(AX),'code_sha256':sha(Path(__file__)),'table5_pdf_pages':[first+1,last],'all_source_numeric_or_dash_rows':len(d),'all_literal_NP_rows':len(literal),'literal_types':literal.settlement_type_raw.value_counts().to_dict(),'literal_regions':literal.source_region_axis_key.nunique(),'aggregate_grains':d.source_row_grain.value_counts().to_dict(),'all_numerical_sex_sums_exact':bool(validsum),'numeric_sex_sum_rows':int(allnum.sum()),'identity_status_counts':l.link_status.value_counts().to_dict(),'numeric_strict_candidates':int(l.eligible_numeric_recovery.sum()),'candidate_original_quality_counts':l.loc[l.eligible_numeric_recovery,'target_original_quality2010'].value_counts().to_dict(),'literal_dash_population_remains_unknown':int(l.population2010_primary_numeric_cell.isna().sum()),'scope_caveats':['All urban settlements plus ruraldistrictcenters/ruralNP>=3000; not all153124ruralNP.','Federalcityregion and subordinate/municipal totals not ownNP. No universal±10 count interval.','Unique typedidentity uses no populationselection; regional/national corpus exactcounts do not certify2010→2021sameboundary.','Alreadyprimary rows are readback controls, never counted asnewrecoveries; candidate layer not yet applied.'],'output_sha256':{p.name:sha(p)for p in B.glob('national_table5_*')if p.is_file()}};(B/'national_table5_parse_link_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False));print(json.dumps(r,ensure_ascii=False,indent=2))
