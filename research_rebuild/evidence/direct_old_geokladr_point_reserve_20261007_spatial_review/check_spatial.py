"""Cached independent own-object spatial corroboration; candidate-only supplement."""
import sys,json,csv,gzip,re
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd
import duckdb
from urllib.parse import unquote
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
sys.path.insert(0,str(ROOT))
from research_rebuild.mass_linkage.wide_wikidata_bindings import rdf_text,qid,parse_point
OUT=Path(__file__).parent;WORK=Path('/workspace/settlements-work/direct_old_geokladr_point_reserve_20261007_spatial_review')
BASE=Path('/workspace/settlements-work/direct_old_geokladr_point_reserve_20261007/candidate_point_uses.csv')
SAMPLE=ROOT/'research_rebuild/evidence/direct_old_geokladr_point_reserve_20261007/fixed_plus_largest_sample.csv'
TSV=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv')
TRUTHY=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')
TOCHNO=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
f=pd.read_csv(BASE,dtype={'historical_okato_2011_raw':str,'historical_okato_2009_raw':str})
codes=set(f.historical_okato_2011_raw);tsv=defaultdict(list)
with TSV.open() as stream:
 for line,row in enumerate(csv.DictReader(stream,delimiter='\t'),2):
  code=rdf_text(row['?okato'])
  if code in codes:tsv[code].append({'qid':qid(row['?item']),'label':rdf_text(row['?label']),'admin':rdf_text(row['?adminLabel']),'admin_qid':qid(row['?admin']),'coord':row['?coord'],'article':rdf_text(row['?article']),'oktmo':rdf_text(row['?oktmo']),'line':line})
qids={r['qid'] for rows in tsv.values() for r in rows};truth=defaultdict(lambda:defaultdict(list));truthfiles=sorted(TRUTHY.glob('batch*.jsonl.gz'))
for path in truthfiles:
 with gzip.open(path,'rt') as stream:
  for line,text in enumerate(stream,1):
   row=json.loads(text);q=qid(row.get('item'));prop=row.get('property','').rsplit('/',1)[-1]
   if q in qids and prop in ['P721','P764','P625','P31','P131','P17']:truth[q][prop].append({'value':row.get('value'),'file':str(path),'line':line,'retrieved_at_utc':row.get('retrieved_at_utc')})
c=duckdb.connect(config={'threads':1,'memory_limit':'350MB'})
t=c.execute('SELECT object_level,object_name,region,mun_upper,settlement,settlement_type_full_dadata,settlement_dadata,okato_dadata,oktmo_dadata,fias_level_dadata,fias_id_dadata,settlement_fias_id_dadata,latitude_dadata,longitude_dadata FROM read_parquet(?) WHERE okato_dadata IN (SELECT UNNEST(?))',[str(TOCHNO),list(codes)]).fetchdf()
tidx={code:d.to_dict('records') for code,d in t.groupby('okato_dadata')}
coorddup=Counter((a,b) for a,b in c.execute('SELECT latitude_dadata,longitude_dadata FROM read_parquet(?) WHERE latitude_dadata IS NOT NULL',[str(TOCHNO)]).fetchall())
fiadup=Counter(v for v, in c.execute('SELECT fias_id_dadata FROM read_parquet(?) WHERE fias_id_dadata IS NOT NULL',[str(TOCHNO)]).fetchall())
localitytypes={'Q486972','Q532','Q5084','Q22674919','Q3957','Q515','Q262166','Q7930989','Q2989453'}
reviews=[];deltas=[]
for a in f.to_dict('records'):
 code=a['historical_okato_2011_raw'];rawpoint=(a['latitude'],a['longitude']);hits=tsv.get(code,[]);reasons=[];witnesses=[]
 cleanq=[]
 for q in sorted({r['qid'] for r in hits}):
  rows=[r for r in hits if r['qid']==q];labels={r['label'] for r in rows};admins={r['admin'] for r in rows};cl=truth[q]
  labelok=any(normalize(v)==normalize(a['settlement_name']) for v in labels)
  article_titles=[unquote(r['article']).rsplit('/',1)[-1].replace('_',' ') for r in rows if r['article']]
  article_counties=[m.group(1) for title in article_titles for m in [re.search(r'\(([^()]*(?:район|округ)[^()]*)\)$',title)] if m]
  county_direct=any(county_key(v)==a['county_key'] for v in admins if v)
  county_article=any(county_key(v)==a['county_key'] for v in article_counties)
  countyok=county_direct or county_article
  p721={str(r['value']) for r in cl.get('P721',[])};truthy_codeok=code in p721;codeok=True # Every hit is a literal TSV own P721 match.
  p31={qid(r['value']) for r in cl.get('P31',[])};typeok=bool(p31&localitytypes)
  pts={p for r in cl.get('P625',[]) if (p:=parse_point(r['value']))[0] is not None}
  tsvpts={p for r in rows if (p:=parse_point(r['coord']))[0] is not None};allpts=pts|tsvpts
  distances=[distance_km(rawpoint,p) for p in allpts]
  qualified=labelok and countyok and codeok
  good=qualified and typeok and len(allpts)==1 and max(distances,default=999)<=5
  witnesses.append({'provider':'Wikidata','qid':q,'url':'https://www.wikidata.org/wiki/'+q,'articles':sorted({r['article'] for r in rows if r['article']}),'tsv_lines':[r['line'] for r in rows],'labels':sorted(labels),'administrative_labels':sorted(admins),'article_titles':article_titles,'article_explicit_county_designators':article_counties,'own_code_exact_TSV_P721':True,'own_code_exact_truthy_P721':truthy_codeok,'own_label_exact':labelok,'own_county_exact':countyok,'county_direct_admin_exact':county_direct,'county_own_article_designator_exact':county_article,'locality_P31':sorted(p31),'locality_type_supported':typeok,'distinct_coordinates':len(allpts),'coordinates':sorted(allpts),'distances_km':distances,'P625_witnesses':cl.get('P625',[]),'P721_witnesses':cl.get('P721',[]),'source_binding_qualified':qualified,'spatial_corroborated':good})
  if qualified and len(allpts)>1:reasons.append('wikidata_multiple_coordinates_hold')
  if qualified and max(distances,default=0)>5:reasons.append('wikidata_qualified_point_conflict_over_5km')
  if good:cleanq.append(q)
 if len({r['qid'] for r in hits})>1:reasons.append('wikidata_exact_code_multiple_entities_hold')
 cleantoch=[]
 for b in tidx.get(code,[]):
  selected_label=normalize(b['settlement']);selected_label=re.sub(r'^(?:деревня|село|поселок|пгт|хутор|станица|город)\s+','',selected_label)
  labelok=normalize(b['settlement_dadata'])==normalize(a['settlement_name']) and selected_label==normalize(a['settlement_name'])
  typeok=normalize(b['settlement_type_full_dadata'])==normalize(a['settlement_type'])
  countyok=county_key(b['mun_upper'])==a['county_key'];idsok=bool(b['fias_id_dadata'] and b['fias_id_dadata']==b['settlement_fias_id_dadata'] and b['fias_level_dadata'] in ['4','6'] and fiadup[b['fias_id_dadata']]==1)
  pointok=pd.notna(b['latitude_dadata']) and pd.notna(b['longitude_dadata']);dist=distance_km(rawpoint,(b['latitude_dadata'],b['longitude_dadata'])) if pointok else None
  qualified=labelok and typeok and countyok and idsok and b['object_level']=='Населенный пункт'
  good=qualified and pointok and coorddup[(b['latitude_dadata'],b['longitude_dadata'])]==1 and dist<=5
  witnesses.append({'provider':'Tochno_Dadata','own_okato_exact':True,'own_label_exact':labelok,'own_type_exact':typeok,'own_county_exact':countyok,'own_fias_tuple_unique':idsok,'raw_object_level':b['object_level'],'own_fias_id':b['fias_id_dadata'],'latitude':b['latitude_dadata'],'longitude':b['longitude_dadata'],'distance_km':dist,'source_binding_qualified':qualified,'spatial_corroborated':good,'source_locator':'okato_dadata='+code+';fias_id_dadata='+str(b['fias_id_dadata']),'raw_own_label':b['settlement_dadata'],'raw_selected_label':b['settlement'],'raw_mun_upper':b['mun_upper']})
  if qualified and dist is not None and dist>5:reasons.append('tochno_qualified_point_conflict_over_5km')
  if good:cleantoch.append(b['fias_id_dadata'])
 if len(tidx.get(code,[]))>1:reasons.append('tochno_exact_code_multiple_rows_hold')
 corroborated=bool(cleanq or cleantoch) and not reasons
 status='independent_own_object_spatial_corroboration_candidate' if corroborated else 'qualified_spatial_conflict_hold' if any('conflict' in r or 'multiple' in r for r in reasons) else 'no_qualified_independent_own_object_point'
 reviews.append({'source_record_id':a['source_record_id'],'census_year':a['census_year'],'settlement_name':a['settlement_name'],'population':a['population'],'county_key':a['county_key'],'raw_own_code':code,'raw_latitude':a['latitude'],'raw_longitude':a['longitude'],'wikidata_own_code_entities':len({r['qid'] for r in hits}),'tochno_own_code_rows':len(tidx.get(code,[])),'qualified_wikidata_qids':'|'.join(cleanq),'qualified_tochno_ids':'|'.join(cleantoch),'spatial_review_status':status,'hold_reasons':';'.join(sorted(set(reasons))),'independent_spatial_witnesses_json':json.dumps(witnesses,ensure_ascii=False,default=str),'coordinate_accuracy_probability_asserted':False,'provider_binding_and_point_agreement_separate':True})
 if corroborated:
  a.update({'target_source_record_id':a['source_record_id'],'target_year':a['census_year'],'independent_spatial_rule':'exact_own_code_label_type_county_unique_independent_point_within5km_no_competition_v1','independent_spatial_witnesses_json':json.dumps(witnesses,ensure_ascii=False,default=str),'admission_allowed':False,'coordinate_admission_status':'candidate_only_requires_independent_review'})
  deltas.append(a)
g=pd.DataFrame(reviews);g.to_csv(WORK/'all_own_code_spatial_screen.csv',index=False)
pd.DataFrame(deltas).to_csv(WORK/'candidate_independently_corroborated_point_delta.csv',index=False)
orig=pd.read_csv(SAMPLE);bounded=pd.concat([orig.head(10),orig.iloc[15:].head(20)]).drop_duplicates('source_record_id')
g[g.source_record_id.isin(bounded.source_record_id)].to_csv(OUT/'top10_plus_fixed20_spatial_review.csv',index=False)
g[g.spatial_review_status.eq('qualified_spatial_conflict_hold')].to_csv(OUT/'qualified_spatial_holds.csv',index=False)
sources=[BASE,SAMPLE,TSV,TOCHNO,*truthfiles]
r={'status':'candidate_only_no_admission','screened_candidate_rows':len(g),'bounded_sample_rows':len(bounded),'bounded_sample_status_counts':g[g.source_record_id.isin(bounded.source_record_id)].spatial_review_status.value_counts().to_dict(),'batch_status_counts':g.spatial_review_status.value_counts().to_dict(),'corroborated_population_by_year':{str(y):int(d.population.sum()) for y,d in g[g.spatial_review_status.eq('independent_own_object_spatial_corroboration_candidate')].groupby('census_year')},'input_hashes':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sources},'generator_sha256':sha(Path(__file__)),'limitations':['No source population, identity graph or accepted coordinate inputs changed.','5km corroboration demonstrates own-object regional agreement, not a quantified accuracy bound or historical measurement.','Wikidata TSV and truthy P625 share a Wikimedia lineage; they count as one external family versus GeoKLADR.','Multiple coordinates are held without selecting a convenient point. No exact code or own label/type/county means no spatial qualification.','No selected current census observation or accepted point is required. Missing qualified corroboration remains unresolved.','No inferred provider QC accuracy probability.']}
r['outputs']={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [*WORK.glob('*.csv'),*OUT.glob('*.csv')]}
(OUT/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:r[k] for k in ['screened_candidate_rows','bounded_sample_rows','bounded_sample_status_counts','batch_status_counts','corroborated_population_by_year']},ensure_ascii=False))
