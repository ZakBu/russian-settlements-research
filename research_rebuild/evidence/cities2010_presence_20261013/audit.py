from pathlib import Path
import fitz,pandas as pd,re,json,hashlib,unicodedata
O=Path(__file__).parent
P=Path('/workspace/scratch/cities2010-audit/raw/pub-11-1-4.pdf')
I=Path('/workspace/scratch/residual-round2-20261013/final/integrated_spatial_temporal_records.parquet')
F=Path('/workspace/russian-settlements-research/publication/stage71/accepted_common_federal_territory_axis.csv')
def norm(s):
 s=unicodedata.normalize('NFKC',str(s)).lower().replace('ё','е').replace('ѐ','е')
 return re.sub(r'\s+',' ',re.sub(r'[^\w\s]',' ',s)).strip()
rows=[]
for pn,page in enumerate(fitz.open(P),1):
 lines=[x.strip() for x in page.get_text().splitlines() if x.strip()]
 n=0
 for j in range(3,len(lines)):
  if re.fullmatch(r'\d+|-',lines[j]) and re.fullmatch(r'\d+|-',lines[j-1]) and not re.fullmatch(r'\d+|-',lines[j-2]):
   # Paired data columns, excluding 2002/2010 header (previous line is table header).
   if lines[j-1]=='2002' and lines[j]=='2010':continue
   region=lines[j-2];name=lines[j-3]
   if region in ['Москва','Санкт-Петербург']:name=region
   n+=1
   rows.append(dict(pdf_page=pn,pdf_row=n,city_raw=name,region_raw=region,population2010=int(lines[j]) if lines[j].isdigit() else None,source_locator=f'pdf_page_{pn}:parsed_city_ordinal={n}'))
a=pd.DataFrame(rows);a['city_clean']=a.city_raw.str.replace(r'\d+\)$','',regex=True);a['name_norm']=a.city_clean.map(norm)
d=pd.read_parquet(I);d=d[d.census_year.eq(2010)];cities=d[d.type_norm.eq('город')]
f=pd.read_csv(F);f=f[f.census_year.eq(2010)]
def rk(s):
 s=norm(s);s=re.sub(r'\b(республика|область|край|автономный|автономная|округ)\b','',s);s=re.sub(r'\s+',' ',s).strip()
 return {'саха якутия':'саха','чувашская':'чувашия','чувашская чувашия':'чувашия','северная осетия алания':'северная осетия алания','ханты мансийский югра':'ханты мансийский югра'}.get(s,s)
cities=cities.copy();cities['audit_name']=cities.settlement_name.map(lambda s:norm(re.sub(r'^г\.\s*','',str(s))));cities['audit_region']=cities.region_norm.map(rk)
# Match independently parsed row to exact native source PDF locator, name, type, raw count.
results=[]
for r in a.itertuples():
 cand=cities[cities.audit_name.eq(r.name_norm)&cities.audit_region.eq(rk(r.region_raw))]
 exact=cand[cand.population.eq(r.population2010)]
 source=exact
 pdfsource=exact[exact.source_record_id.str.startswith(f'2010:pub-11-1-4.pdf:pdf_page_{r.pdf_page}:')]
 fed=f[f.territory_name.map(norm).eq(r.name_norm)&f.territory_population.eq(r.population2010)]
 results.append(dict(**r._asdict(),native_candidates=len(cand),exact_count_candidates=len(exact),exact_pdf_candidates=len(pdfsource),source_record_ids='|'.join(source.source_record_id),native_source_hashes='|'.join(source.source_sha256.fillna('').astype(str)),native_source_locators='|'.join(source.source_locator.fillna('').astype(str)),native_source_files='|'.join(source.source_file.fillna('').astype(str)),native_raw_point_present=bool(source.latitude.notna().all()&source.longitude.notna().all()) if len(source) else False,native_regions='|'.join(source.region_norm),native_types='|'.join(source.type_norm),native_okato='|'.join(source.okato.fillna('').astype(str)),native_oktmo='|'.join(source.oktmo.fillna('').astype(str)),native_working_credit=bool(source.working_credit_present.all()) if len(source) else False,federal_present=len(fed)>0,status='federal_territory' if len(fed) else ('native_exact_pdf_city_count' if len(pdfsource)==1 else 'native_exact_primary_city_count') if len(source)==1 else 'review'))
z=pd.DataFrame(results);z.to_csv(O/'official_city_roster_comparison.csv.gz',index=False);z[z.population2010.ge(10000)].to_csv(O/'large_cities_ge10000.csv',index=False)
z[z.status.eq('review')].to_csv(O/'exceptions.csv',index=False)
pins=[dict(path=str(x),sha256=hashlib.sha256(x.read_bytes()).hexdigest(),bytes=x.stat().st_size) for x in [P,I,F]]
s=dict(official_roster_rows=len(a),official_population_sum=int(a.population2010.sum()),native_city_population_sum=int(cities.population.sum()),native_city_rows=len(cities),large_official_rows=int(a.population2010.ge(10000).sum()),large_status_counts=z[z.population2010.ge(10000)].status.value_counts().to_dict(),all_status_counts=z.status.value_counts().to_dict(),large_uncredited_nonfederal=z[z.population2010.ge(10000)&~z.federal_present&~z.native_working_credit].city_clean.tolist(),source_pins=pins,raw_archive_member='data/raw/2010_official_tom11/pub-11-1-4.pdf',matching_rule='Independent PDF parse; exact normalized name, city type, published count, same region; exact PDF page source ID when retained, otherwise native replacement provenance; federal subjects separately checked. No new links or counts admitted.')
(O/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2));print(json.dumps(s,ensure_ascii=False,indent=2))
