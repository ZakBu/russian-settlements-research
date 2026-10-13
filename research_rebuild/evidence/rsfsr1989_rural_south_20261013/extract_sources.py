"""Reproduce primary rural NP 1989 extracts; never allocate district totals."""
from pathlib import Path
import re, hashlib, json
import pandas as pd
import xlrd
BASE=Path('/workspace/shared/rsfsr1989_rural_south')
OUT=Path(__file__).parent
SOURCE_STAV='https://web.archive.org/web/20150112114215id_/http://stavrop.gks.ru/perepis/vpn2002/informaciya/Cis89_02.zip'
SOURCE_ROST='https://web.archive.org/web/20201020022150id_/https://rostov.gks.ru/storage/mediabank/1.%D0%A7%D0%B8%D1%81%D0%BB%D0%B5%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D1%8C%2B%D0%B8%2B%D1%80%D0%B0%D0%B7%D0%BC%D0%B5%D1%89%D0%B5%D0%BD%D0%B8%D0%B5%2B%D0%BD%D0%B0%D1%81%D0%B5%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F%2B%D0%A0%D0%BE%D1%81%D1%82%D0%BE%D0%B2%D1%81%D0%BA%D0%BE%D0%B9%2B%D0%BE%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D0%B8.pdf'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return re.sub(r'[^а-яa-z0-9]+',' ',s.lower().replace('ё','е').replace('ѐ','е')).strip()
rows=[];b=xlrd.open_workbook(BASE/'Cis89_02.xls',formatting_info=True);s=b.sheet_by_index(0);district='';admin=''
for i in range(5,1143):
 r=s.row_values(i);name=r[1].strip()
 if re.fullmatch(r'[А-ЯЁа-яё -]+ район',name):district=name
 if str(r[0]).startswith('074') and name.startswith('г. '):district='город '+name[3:]
 if 'сельсовет' in name.lower() and not name.startswith('Сельсоветы'):admin=name
 m=re.match(r'^(село|станица|аул|хутор|посёлок) (.+)',name)
 if not m:continue
 font=b.font_list[b.xf_list[s.cell_xf_index(i,1)].font_index]
 note=re.findall(r'\d+\)|\*+\)',m[2]);clean=re.sub(r'\([^)]*\)|\d+\)|\*+\)','',m[2]).strip();clean=re.sub(r'\s+',' ',clean)
 adjusted=bool(font.bold or '5)' in note)
 rows.append(dict(source_record_id=f'stavropol1989:Cis89_2002:{i+1}',census_year=1989,region_norm='ставропольский',district_raw=district,administration_raw=admin,settlement_name=clean,settlement_type=m[1],name_norm=norm(clean),type_norm=norm(m[1]),population=int(r[2]),population_2002=int(r[3]),male_1989=int(r[5]),female_1989=int(r[8]),okato=r[0],source_file='Cis89_02.xls',source_sha256=sha(BASE/'Cis89_02.xls'),source_url=SOURCE_STAV,source_locator=f'Cis89_2002!A{i+1}:K{i+1}',source_name_raw=name,footnote=';'.join(note),post1989_territorial_adjustment=adjusted,formed_or_restored_post1989=bool(font.italic),urban_in_1989=False,population_scope='settlement_both_sexes',is_additive_settlement_record=not adjusted and not font.italic,population_value_quality='territory_adjusted_1989' if adjusted else 'reported_census_integer'))
# Rostov table9, printed pages17-73. Preserve district and local administration hierarchy.
text=(BASE/'rostov20201020.txt').read_text();start=text.index('9. Численность населения, проживающего');block=text[start:];block=block[:block.index('10. Изменения')]
pat=re.compile(r'^\s*((?:хутор|село|станица|слобода|пос[еѐё]лок|станция|разъезд|деревня) .*?)\s+(\d+|…)\s+(\d+|…)\s+(\d+|…)\s+(\d+|…)\s+(\d+|…)\s+(\d+|…)\s*$')
short={'хутор Матюшенский':[7,1,3,None,4,1],'хутор Николаевский':[2,1,1,1,1,None],'разъезд Дяткино':[13,2,6,2,7,None],'хутор Новодонской':[59,1,28,1,31,None]}
urban_pairs={('Багаевская','Багаевский район'),('Веселый','Веселовский район'),('Зимовники','Зимовниковский район'),('Восход','Мартыновский район'),('Большая Мартыновка','Мартыновский район'),('Южный','Мартыновский район'),('Матвеев Курган','Матвеево-Курганский район'),('Орловский','Орловский район'),('Михайлов','Тацинский район'),('Тацинская','Тацинский район'),('Целина','Целинский район'),('Чертково','Чертковский район')}
district='';admin='';printed_page=17
for idx,line in enumerate(block.splitlines(),1):
 if re.fullmatch(r'\s*\d{2}\s*',line):printed_page=int(line)
 dm=re.match(r'^\s*([А-ЯЁа-яё -]+ район)(?:\d+\))?\s+\d',line)
 if dm:district=dm[1].strip();admin=''
 if 'сельсовет' in line.lower():admin=line.strip()
 match=pat.match(line);manual=False
 if match:raw=match[1];vals=[int(x) if x.isdigit() else None for x in match.groups()[1:]]
 else:
  candidates=[k for k in short if line.strip().startswith(k+' ')];
  if not candidates:continue
  raw=candidates[0];vals=short[raw];manual=True
 typ,name=raw.split(' ',1);typ=typ.replace('ѐ','ё');note=re.findall(r'\d+\)',name);name=re.sub(r'\d+\)','',name).strip()
 isurban=(name,district) in urban_pairs
 rows.append(dict(source_record_id=f'rostov1989:table9:line{idx}',census_year=1989,region_norm='ростовская',district_raw=district,administration_raw=admin,settlement_name=name,settlement_type=typ,name_norm=norm(name),type_norm=norm(typ),population=vals[0],population_2002=vals[1],male_1989=vals[2],female_1989=vals[4],okato=None,source_file='rostov20201020.pdf',source_sha256=sha(BASE/'rostov20201020.pdf'),source_url=SOURCE_ROST,source_locator=f'Table9; block line{idx}; page approximately{printed_page}',source_name_raw=raw,footnote=';'.join(note),post1989_territorial_adjustment=False,formed_or_restored_post1989=False,urban_in_1989=isurban,population_scope='settlement_both_sexes',is_additive_settlement_record=vals[0] is not None and not isurban,population_value_quality='missing_1989' if vals[0] is None else 'reported_census_integer',extraction_note='2002 zero sex cell absent; 1989 total and sex values explicitly present' if manual else 'six explicit values'))
df=pd.DataFrame(rows);df['sex_total_valid']=df.population.eq(df.male_1989+df.female_1989)
df.to_csv(OUT/'primary_rural_1989_all_rows.csv',index=False)
usable=df[df.is_additive_settlement_record & df.population.gt(0) & df.sex_total_valid].copy();usable.to_csv(OUT/'primary_rural_1989_usable.csv',index=False)
summary={}
for region,g in df.groupby('region_norm'):
 u=usable[usable.region_norm.eq(region)]
 summary[region]={'all_np_rows':len(g),'explicit_1989_population_rows':int(g.population.notna().sum()),'all_explicit_1989_people':int(g.population.sum()),'usable_rows':len(u),'usable_people':int(u.population.sum()),'sex_total_failed_explicit':int((g.population.notna() & ~g.sex_total_valid).sum()),'urban_1989_rows':int(g.urban_in_1989.sum()),'urban_1989_people':int(g.loc[g.urban_in_1989,'population'].sum()),'territory_adjusted_rows':int(g.post1989_territorial_adjustment.sum()),'territory_adjusted_people':int(g.loc[g.post1989_territorial_adjustment,'population'].sum())}
(OUT/'coverage_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))
