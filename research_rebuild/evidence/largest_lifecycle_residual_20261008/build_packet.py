"""Replay bounded own-NP appearances; predecessor contexts never credited as children."""
from pathlib import Path
import csv,gzip,json,hashlib,math,subprocess
import pandas as pd
import xlrd
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).resolve().parent; E=ROOT/'research_rebuild/evidence'
REG=E/'main_axis_residual_registry_20261008/primary_axis_remaining_source_records.csv.gz'
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
CACHE=E/'large_observed_year_recovery_20261007/own_pages.json.gz'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(fn,rows):
 assert rows
 pd.DataFrame(rows).to_csv(OUT/fn,index=False)
def distance(a,b):
 la,lo,lb,lob=map(math.radians,[*a,*b]);return 6371.0088*2*math.asin(min(1,math.sqrt(math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lob-lo)/2)**2)))
def main():
 pins={str(p):sha(p) for p in [REG,SEL,CACHE,OUT/'innopolis_wiki.json.gz']}
 receipt=json.loads((E/'main_axis_residual_registry_20261008/receipt.json').read_text());assert pins[str(REG)]==receipt['output_pins'][REG.name]['sha256']
 r=pd.read_csv(REG,keep_default_na=False,low_memory=False);r['population']=pd.to_numeric(r.population,errors='coerce');assert r.source_record_id.is_unique
 for y,s in receipt['by_year'].items():
  rr=r[r.census_year==int(y)];assert len(rr)==s['remaining_selected_source_ids'];assert int(rr.population.sum())==s['remaining_selected_population']
 d=pd.read_parquet(SEL);idx=d.set_index('source_record_id');pages=json.load(gzip.open(CACHE,'rt'))['query']['pages'];ip=json.load(gzip.open(OUT/'innopolis_wiki.json.gz','rt'))['query']['pages'][0]
 specs=[('Сириус','Сириус (посёлок городского типа)','appeared_by_formation_from_parent_territory','2020','year',('Посёлок образован в 2020','1 февраля 2020','присвоении географическому объекту наименования'),[2021],('Сочи','краснодарский')),
 ('Звездный городок','Звёздный городок','appeared_in_separate_publication_existing_military_settlement','2009-01-19','day',('До 2009 года населенный пункт именовался','на основе военного городка было создано','Ранее население Звёздного городка учитывалось в составе населения города Щёлково'),[2010,2021],('Щёлково','московская')),
 ('Иннополис','Иннополис','appeared_new_settlement_after_2010','2012-12-24','day',('Иннополис основали 9 июня 2012','24 декабря принял постановление', 'В апреле 2013',' |date         = 2012-12-24'),[2021],None)]
 events=[];own=[];states=[];points=[];credit=[];context=[];edges=[];excerpts=[];checks=[]
 raw21=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');pins[str(raw21)]=sha(raw21)
 frame=pd.read_parquet(raw21,columns=['object_level','object_name','settlement','population','oktmo','latitude_dadata','longitude_dadata'])
 for name,title,rel,date,precision,needles,years,parent in specs:
  page=ip if title=='Иннополис' else next(p for p in pages if p['title']==title);pfile=OUT/'innopolis_wiki.json.gz' if title=='Иннополис' else CACHE;rev=page['revisions'][0];t=rev['slots']['main']['content'];locator=f"page{page['pageid']}:revision{rev['revid']}";scope='own_appearance_'+('star_city' if name=='Звездный городок' else 'sirius' if name=='Сириус' else 'innopolis')
  for needle in needles:
   start=t.index(needle);a=max(t.rfind('\n',0,start),0);b=t.find('\n',start);b=len(t) if b<0 else b
   excerpts.append(dict(scope_id=scope,source_file=str(pfile),source_sha256=sha(pfile),source_locator=locator,revision_timestamp=rev['timestamp'],literal_needle=needle,wikitext_char_start=a,wikitext_char_end=b,exact_excerpt=t[a:b]))
  actual=r[r.settlement_name.eq(name)&r.census_year.isin(years)];assert len(actual)==len(years) and set(actual.census_year)==set(years);assert actual.has_own_point.eq(True).all()
  co=page['coordinates'];assert len(co)==1
  events.append(dict(scope_id=scope,place=name,relation=rel,event_date=date,date_precision=precision,decision_status='accepted_secondary_literal_own_NP_lifecycle',event_source_file=str(pfile),event_source_sha256=sha(pfile),event_source_locator=locator,primary_act_reopened=False,ordinary_same_place=False,boundary_comparability='UNKNOWN',own_actual_observed_years=','.join(map(str,years)),predecessor_population_allocated=False,physical_creation_asserted=name=='Иннополис',date_role='Naming/municipal formation chronology, not exact physical census boundary' if name=='Сириус' else 'Existing military settlement transformed into ZATO; publication separated from2010' if name=='Звездный городок' else 'Secondary article dates new NP creation resolution24Dec2012; later2015 city status distinct'))
  for row in actual.to_dict('records'):
   sid=row['source_record_id'];s=idx.loc[sid];assert s.population==row['population'];assert s.is_additive_settlement_record
   lat,lon=float(row['accepted_own_latitude']),float(row['accepted_own_longitude']);assert distance((lat,lon),(co[0]['lat'],co[0]['lon']))<5
   if row['census_year']==2021:
    raw=frame.iloc[int(s.source_row)-1];assert raw.object_level=='Населенный пункт';assert int(raw.population)==int(s.population);assert str(raw.oktmo)==str(s.oktmo)
    path=raw21;loc=f'parquet physical row0based={int(s.source_row)-1}; published locator1based={int(s.source_row)}';literal=raw.to_json(force_ascii=False)
   else:
    path=Path('/workspace/settlements-raw')/s.source_file;pins[str(path)]=sha(path);vals=xlrd.open_workbook(str(path)).sheet_by_name(s.source_sheet).row_values(int(s.source_row)-1);assert vals[4]==s.population and 'Звездный городок' in vals[3];loc=f'{s.source_sheet}!row1based={int(s.source_row)}';literal=json.dumps(vals[:5],ensure_ascii=False)
   checks.append(dict(source_record_id=sid,census_year=row['census_year'],source_path=str(path),source_sha256=sha(path),source_locator=loc,exact_raw_excerpt=literal,raw_matches_selected=True,population_quality_preserved=s.population_value_quality))
   own.append(dict(scope_id=scope,source_record_id=sid,year=row['census_year'],place=name,native_population=s.population,native_population_quality=s.population_value_quality,own_actual_observation=True,population_boundary_comparability='UNKNOWN',ordinary_three_census_identity=False))
   pointpath=Path(row['point_origin_file']);assert pointpath.exists();pins[str(pointpath)]=sha(pointpath)
   points.append(dict(scope_id=scope,target_source_record_id=sid,latitude=lat,longitude=lon,point_origin_file=str(pointpath),point_origin_sha256=sha(pointpath),own_point_existing_accepted=True,new_point_admission=False,independent_own_article_source=str(pfile),independent_own_article_locator=locator+':coordinates[0]',independent_article_latitude=co[0]['lat'],independent_article_longitude=co[0]['lon'],distance_km=distance((lat,lon),(co[0]['lat'],co[0]['lon'])),temporal_interpretation='Physical own-NP reference point, not census-day boundary'))
   credit.append(dict(scope_id=scope,source_record_id=sid,year=row['census_year'],source_population=s.population,new_population_on_separate_transformation_path_axis=s.population,own_historical_point_verified=True,already_in_stage61_primary_axis=False,is_additive_to_original_final_mixed_census_axis=False,ordinary_three_census_same_place_claim=False))
  for year in (2002,2010,2021):
   status='actual_own_published_observation' if year in years else 'not_separately_published_in_parent_city_known_own_count_unknown' if name=='Звездный городок' else 'outside_own_NP_coverage_before_formation'
   states.append(dict(scope_id=scope,place=name,year=year,status=status,own_population=next((z['native_population'] for z in own if z['scope_id']==scope and z['year']==year),''),unknown_is_zero=False,physical_absence_asserted=False,parent_population_is_own=False,boundary_comparability='UNKNOWN'))
  if parent:
   pp=d[d.settlement_type.eq('город')&d.region_norm.eq(parent[1])&d.name_norm.eq(parent[0].lower().replace('ё','е'))];assert len(pp)==3
   for row in pp.to_dict('records'):
    path=Path('/workspace/settlements-raw')/row['source_file'];pins[str(path)]=sha(path)
    if row['census_year']==2002:
     vals=xlrd.open_workbook(str(path)).sheet_by_index(0).row_values(int(row['source_row'])-1);assert float(vals[1])==row['population'];literal=json.dumps(vals[:4],ensure_ascii=False);loc=f'0!row1based={int(row["source_row"])}'
    elif row['census_year']==2010:
     page_no=int(row['source_sheet'].rsplit('_',1)[1]);txt=subprocess.check_output(['pdftotext','-layout','-f',str(page_no),'-l',str(page_no),str(path),'-']).decode();lines=[z for z in txt.splitlines() if ('Сочи' if parent[0]=='Сочи' else 'лково') in z];assert len(lines)==1 and str(int(row['population'])) in lines[0].replace(' ','');literal=lines[0];loc=f'PDFpage={page_no}'
    else:
     raw=frame.iloc[int(row['source_row'])-1];assert raw.object_level=='Населенный пункт' and raw.population==row['population'];literal=raw.to_json(force_ascii=False);loc=f'parquet physical row0based={int(row["source_row"])-1}'
    context.append(dict(scope_id=scope,parent_city=parent[0],census_year=row['census_year'],source_record_id=row['source_record_id'],population=row['population'],population_quality=row['population_value_quality'],source_path=str(path),source_sha256=sha(path),source_locator=loc,exact_raw_excerpt=literal,context_only=True,new_source_UID_credit=0,parent_count_copied_to_child=False,boundary_comparability='UNKNOWN'))
    if row['census_year']<min(years):edges.append(dict(scope_id=scope,from_source_record_id=row['source_record_id'],to_source_record_id=actual[actual.census_year==min(years)].iloc[0].source_record_id,relation='published_parent_population_context_before_separate_appearance' if name=='Звездный городок' else 'formed_from_parent_city_territory_context',event_date=date,same_place=False,graph_union_allowed=False,parent_source_UID_credit=0,boundary_comparability='UNKNOWN'))
 for fn,rs in [('accepted_lifecycle_events.csv',events),('accepted_own_sourceyear_observations.csv',own),('accepted_own_point_references.csv',points),('accepted_available_year_statuses.csv',states),('accepted_typed_context_edges.csv',edges),('actual_parent_city_three_year_context_only.csv',context),('accepted_source_UID_credit_union.csv',credit),('literal_own_source_excerpts.csv',excerpts),('native_raw_row_witnesses.csv',checks)]:write(fn,rs)
 review=[]
 for row in r.sort_values('population',ascending=False).head(30).to_dict('records'):
  disposition='bounded accepted available-year own-NP lifecycle packet' if row['settlement_name'] in [x[0] for x in specs] else 'regional_worker county/spelling hold; no rename guessed' if row['settlement_name'] in ['Илсхан-Юрт','Иласхан-Юрт'] else 'outside bounded lifecycle scope; no event admitted'
  review.append({k:row[k] for k in ['source_record_id','census_year','settlement_name','region_norm','population','component_years']}|dict(disposition=disposition))
 write('top30_dispositions.csv',review)
 pop={str(y):int(sum(z['source_population'] for z in credit if z['year']==y)) for y in [2002,2010,2021]}
 outputs={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in OUT.glob('*.csv')}
 receipt_out=dict(status='reviewed_bounded_own_appearance_packet_root_replay_pending',baseline='stage61 exact source_UID main_axis_residual_registry',baseline_report_sha256=receipt['baseline_report_sha256'],baseline_by_year=receipt['by_year'],input_pins=pins,output_pins=outputs,accepted_lifecycle_events=len(events),candidate_for_root_credit_source_UIDs=len(credit),conditional_new_source_UID_population_by_year=pop,parent_city_context_source_UIDs=len(context),parent_context_new_credit=0,ordinary_graph_edges_added=0,new_point_admissions=0,unknown_populations_imputed=0,whole_parent_allocations=0,known_secondary2010_star_city_6332_discrepancy='Selected protected2010=6333 retained; no6332 substitution',boundary_comparability='UNKNOWN',primary_act_reopened=False,limitation='Secondary literal own-article event chronology; failed official endpoints503. Root must replay exact UID union; no global coverage gain asserted here.')
 (OUT/'packet_receipt.json').write_text(json.dumps(receipt_out,ensure_ascii=False,indent=2));assert sum(p.stat().st_size for p in OUT.iterdir() if p.is_file())<2_000_000
 print(json.dumps(dict(conditional_credit=pop,credit_UIDs=len(credit),context_UIDs=len(context),packet_bytes=sum(p.stat().st_size for p in OUT.iterdir() if p.is_file()))))
if __name__=='__main__':main()
