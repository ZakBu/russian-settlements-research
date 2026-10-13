from pathlib import Path
import json,gzip,re,hashlib
import pandas as pd,duckdb,xlrd
O=Path(__file__).parent;E=O.parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();r=json.load(open(O/'application_receipt.json'))
for p,h in r['input_pins'].items():assert sha(p)==h,p
for name,h in r['output_pins'].items():assert sha(O/name)==h,name
f=pd.read_csv(O/'accepted_qualified_physical_observations.csv',keep_default_na=False);n=f[f.year.ne(2010)];sec=f[f.year.eq(2010)];edge=pd.read_csv(O/'accepted_identity_edge_delta.csv',keep_default_na=False);point=pd.read_csv(O/'accepted_point_use_delta.csv',keep_default_na=False);credits=pd.read_csv(O/'accepted_qualified_native_source_ID_credit_union.csv');assert len(f)==3*f.trajectory_id.nunique() and not f[['trajectory_id','year']].duplicated().any();assert sec.source_record_id.eq('').all() and sec.nonadditive_observation.all();assert not f.ordinary_NP3_asserted.any() and not f.boundary_comparability_asserted.any();assert f.accepted_physical_three_observed_census_year_path.all();assert n.source_record_id.is_unique and credits.source_record_id.is_unique;assert set(n.source_record_id)==set(credits.source_record_id);assert edge.from_source_record_id.is_unique and edge.to_source_record_id.is_unique;assert point.target_source_record_id.is_unique
allnative=set(n.source_record_id)|set(edge.from_source_record_id)|set(edge.to_source_record_id);cohort=pd.read_csv(O/'current44_disjoint_missing2010.csv.gz',keep_default_na=False).set_index('current_source_record_id');allnative.update(cohort.loc[list(edge.to_source_record_id),'native2002_source_record_id']);selected='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet';c=duckdb.connect(config={'threads':1,'memory_limit':'200MB'});obs=c.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,population,population_value_quality,source_file,source_locator,okato,oktmo from read_parquet(?)where source_record_id in(select unnest(?))',[selected,list(allnative)]).fetchdf().set_index('source_record_id');assert len(obs)==len(allnative)
for x in n.to_dict('records'):
 a=obs.loc[x['source_record_id']];assert int(a.census_year)==int(x['year']);assert float(a.population)==float(x['population_source_value']);assert a.population_value_quality==x['population_quality']
cache={};labels={};physical={'Q532','Q5084','Q486972','Q2514025','Q15078955','Q24258416','Q27062006','Q27517483'}
for p in r['input_pins']:
 if not(p.endswith('.json')or p.endswith('.json.gz')):continue
 try:b=Path(p).read_bytes();d=json.loads(gzip.decompress(b)if p.endswith('.gz')else b);es=d.get('entities',d.get('payload',{}).get('entities',{}))
 except:continue
 if not isinstance(es,dict):continue
 for q,e in es.items():
  if isinstance(e,dict)and e.get('labels',{}).get('ru'):labels[q]=e['labels']['ru']['value']
for x in sec.to_dict('records'):
 p=x['source_path']
 if p not in cache:
  raw=Path(p).read_bytes();payload=json.loads(gzip.decompress(raw)if p.endswith('.gz')else raw);cache[p]=payload.get('entities',payload.get('payload',{}).get('entities',{}))
 e=cache[p][x['wikidata_id']];st=next(s for s in e['claims']['P1082']if s.get('id')==x['statement_id']);assert float(st['mainsnak']['datavalue']['value']['amount'])==float(x['population_source_value']);assert st.get('rank')!='deprecated' and not st.get('qualifiers',{}).get('P518');dates=[v.get('datavalue',{}).get('value',{})for v in st.get('qualifiers',{}).get('P585',[])];assert any(v.get('time')==x['declared_date'] and v.get('precision')==int(x['date_precision']) for v in dates);assert x['declared_date'].startswith('+2010')
 p31={v.get('mainsnak',{}).get('datavalue',{}).get('value',{}).get('id')for v in e.get('claims',{}).get('P31',[])if v.get('rank')!='deprecated'};assert p31&physical
 methods=[v.get('datavalue',{}).get('value',{}).get('id')for v in st.get('qualifiers',{}).get('P459',[])];texts=json.loads(x['census_reference_titles_json'])+json.loads(x['reference_urls_json'])+[labels.get(q,'')for q in json.loads(x['P248_ids_json'])];proof=(x['declared_date'].startswith('+2010-10-14')and int(x['date_precision'])>=11)or any(labels.get(m)=='перепись населения'for m in methods)or any(re.search('перепис|census|впн|vpn2010',t,re.I)and'2010'in t for t in texts);assert proof
for x in edge.to_dict('records'):
 p=json.loads(x['source_binding_proof']);literal=p['raw_native_literal_row_witness'];path=Path(literal['source_path']);assert sha(path)==literal['raw_sha256'];sh=xlrd.open_workbook(str(path),on_demand=True).sheet_by_name(literal['sheet']);row=sh.row_values(literal['row1based']-1);assert row==literal['raw_row_values'];assert obs.loc[x['from_source_record_id'],'population']==p['native_source_count_unmodified'];assert p['native2010_own_alias_or_label_positive'] and p['native2010_current_physical_type_positive'];assert p['native2010_source_county_positive'] or p['native2010_own_code_positive'];assert json.loads(p['same_type_same_or_unresolved_county_rivals_json'])==[]
for x in point.to_dict('records'):assert sha(x['point_origin_file'])==x['point_origin_sha256'] and x['coordinate_admission_status']=='reviewed_extension_rule_accepted'
obs.reset_index().to_csv(O/'all_retained_native_observation_pins.csv.gz',index=False,compression={'method':'gzip','mtime':0});previous=set();unionpins={}
for name in ['complete_publisher_partition_members.csv','qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','direct_inclusion_transformation_path_native_credit_union.csv']:
 p=E/'working_full_chain_20261007'/name
 if p.exists():
  a=pd.read_csv(p,dtype=str,keep_default_na=False)
  if 'source_record_id'in a:previous.update(a.source_record_id)
  unionpins[str(p)]=sha(p)
qover=set(credits.source_record_id)&previous;nativeids=set(edge.from_source_record_id)|set(edge.to_source_record_id)|set(cohort.loc[list(edge.to_source_record_id),'native2002_source_record_id']);nover=nativeids&previous;assert not qover and not nover,(qover,nover);assert not nativeids&set(credits.source_record_id)
out={'status':'all_literal_secondary2010_statement_amount_date_precision_census_method_or_reference_physicalP31_and_original_native_counts_quality_verified','baseline_stage':44,'native_accepted_edges':len(edge),'qualified_series':f.trajectory_id.nunique(),'original_native_observations_verified':len(allnative),'secondary2010_native_UID_credit':0,'ordinary_NP3_from_secondary_asserted':False,'native_and_qualified_UIDs_disjoint':True,'current_report_supplemental_credit_overlap':[],'current_report_supplemental_union_input_pins':unionpins,'application_receipt_sha256':sha(O/'application_receipt.json'),'native_pins_sha256':sha(O/'all_retained_native_observation_pins.csv.gz')};(O/'verification_receipt.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in out.items()if k!='current_report_supplemental_union_input_pins'},ensure_ascii=False))
