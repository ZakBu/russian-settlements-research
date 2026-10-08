import sys,json,re,gzip,math,importlib.util
from pathlib import Path
from collections import defaultdict
import pandas as pd,xlrd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(34);before=s.metrics()
sp=importlib.util.spec_from_file_location('finite',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm);bf=fm.finite_metrics(s)
f=pd.read_csv(O/'native_alias_potential.csv',dtype=str,keep_default_na=False);meta=duckdb.connect().execute("select source_record_id,entity_grain_status,source_sheet,source_row from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')").fetchdf().set_index('source_record_id')
county_map=defaultdict(set);oldmap={};newmap={}
for _,a in s.obs[s.obs.census_year.eq(2002)].iterrows():oldmap[s.uf.find(a.source_record_id)]=a
for _,n in s.obs[s.obs.census_year.eq(2021)].iterrows():newmap[s.uf.find(n.source_record_id)]=n
for root,n in newmap.items():
 a=oldmap.get(root)
 if a is not None:county_map[(a.region_norm,county_key(a.district_raw))].add(county_key(n.district_raw))
edges=[];points=[];proof=[];holds=[];checks=[];comp=[];pins={};books={};ents={};seen=set()
for z in f.to_dict('records'):
 a=s.by_id.loc[z['old_source_record_id']];n=s.by_id.loc[z['trajectory_current_source_record_id']];case=z['qid']+':'+a.settlement_name;why=[];root=s.uf.find(n.source_record_id);ar=s.uf.find(a.source_record_id)
 if ar==root:why.append('Already admitted same native component at actual34')
 if s.years[root]!={2010,2021} or s.years[ar]!={2002}:why.append('Actual34 component is not missing02 current2year plus standalone native02')
 if a.source_record_id in seen:why.append('Duplicate proposed old native target')
 if not a.is_additive_settlement_record or not math.isfinite(a.population) or re.search('aggregate|municipal|unresolved|control.total',str(meta.loc[a.source_record_id].entity_grain_status),re.I):why.append('Native source not resolved finite ownNP leaf')
 donor=s.point_rows.get(n.source_record_id)
 if not donor:why.append('No independently admitted own current point')
 ep=Path(z['entity_file']);pins[str(ep)]=sha(ep)
 if str(ep) not in ents:
  x=json.load(gzip.open(ep,'rt'));ents[str(ep)]=x.get('entities',x.get('payload',{}).get('entities',{}))
 e=ents[str(ep)][z['qid']];qpts=[c['mainsnak']['datavalue']['value'] for c in e.get('claims',{}).get('P625',[]) if c.get('rank')!='deprecated' and c.get('mainsnak',{}).get('datavalue',{}).get('type')=='globecoordinate']
 if donor and not any(distance_km((donor['latitude'],donor['longitude']),(p['latitude'],p['longitude']))<=5 for p in qpts):why.append('Current own native-code point not corroborated within5km by independently coded ownQID')
 cc=county_key(n.district_raw);oc=county_key(a.district_raw);ok=bool(oc and (oc==cc or cc in county_map[(a.region_norm,oc)]));scope='Native02/current own printed county direct or independently accepted native county crosswalk' if ok else ''
 rawpath=Path('/workspace/settlements-raw')/a.source_file;pins[str(rawpath)]=sha(rawpath)
 if str(rawpath) not in books:books[str(rawpath)]=xlrd.open_workbook(rawpath)
 bk=books[str(rawpath)];mm=meta.loc[a.source_record_id];sh=bk.sheet_by_name(str(mm.source_sheet));row=int(mm.source_row)-1;rv=sh.row_values(row);parents=[]
 for i in range(max(0,row-350),row):
  for v in sh.row_values(i):
   if isinstance(v,str) and re.search('район|кожуун|улус|сельсовет|сельский округ|город ',v,re.I):parents.append({'row_1based':i+1,'literal':v})
 if not ok:
  major=[p for p in parents if re.search('район|кожуун|улус|город ',p['literal'],re.I)]
  if major:
   owncity=re.search(r'г\.\s*([^,;]+)',major[-1]['literal'],re.I)
   if owncity and re.search(r'(?<!\w)'+re.escape(normalize(owncity.group(1)))+r'(?!\w)',normalize(n.district_raw)):
    ok=True;scope='Actual native02 printed subordinate source parent exact own city token '+json.dumps(major[-1],ensure_ascii=False)
 if not ok:why.append('No independent native02 printed county/current county binding')
 opts=f[f.trajectory_current_source_record_id.eq(n.source_record_id)]
 compatible=[]
 for _,zz in opts.iterrows():
  aa=s.by_id.loc[zz.old_source_record_id];ac=county_key(aa.district_raw)
  if len(opts)==1 or (ac and (ac==cc or cc in county_map[(aa.region_norm,ac)])):compatible.append(aa.source_record_id)
 if compatible!=[a.source_record_id]:why.append('Own-name alias has multiple compatible native02 county competitors')
 existing=s.point_rows.get(a.source_record_id)
 if donor and existing and distance_km((donor['latitude'],donor['longitude']),(existing['latitude'],existing['longitude']))>5:why.append('Existing native02 point conflict; no coordinate rejection in this alias batch')
 li=next((i for i,v in enumerate(rv) if isinstance(v,str) and normalize(a.settlement_name) in normalize(v)),None);vals=[]
 if li is not None:
  for v in rv[li+1:]:
   st=str(v).replace(' ','').replace('\xa0','').replace(',','.')
   if re.fullmatch('[0-9]+(?:\\.[0-9]+)?',st):vals.append(float(st))
 if li is None or not vals or vals[0]!=float(a.population):why.append('Original raw native02 label/first population not recovered unchanged')
 if why:holds.append({'case':case,'old_source_record_id':a.source_record_id,'current_source_record_id':n.source_record_id,'native02_population':a.population,'reason':'; '.join(why)});continue
 checks.append({'case':case,'source_record_id':a.source_record_id,'source_path':str(rawpath),'source_sha256':pins[str(rawpath)],'source_sheet':mm.source_sheet,'source_row_1based':row+1,'literal_raw_row':json.dumps(rv,ensure_ascii=False),'literal_source_parents':json.dumps(parents,ensure_ascii=False),'unchanged_native_population':a.population,'unchanged_native_quality':a.population_value_quality,'native_grain':mm.entity_grain_status,'current_native_okato':n.okato,'current_native_oktmo':n.oktmo,'old_source_own_code_present':bool(a.okato or a.oktmo),'native02_county_binding_rule':scope})
 proof.append(dict(z,native02_county_binding_rule=scope,current_donor_point_json=json.dumps(donor,ensure_ascii=False),raw_own_entity_json=json.dumps(e,ensure_ascii=False),dated_population_used_only_as_corroboration=True,all_alias_region_competitors=opts.old_source_record_id.str.cat(sep=';')))
 for _,peer in s.obs[s.obs.region_norm.eq(a.region_norm)&s.obs.name_norm.isin({a.name_norm,n.name_norm})].iterrows():
  pp=s.point_rows.get(peer.source_record_id);comp.append({'case':case,'source_record_id':peer.source_record_id,'year':peer.census_year,'name':peer.settlement_name,'type':peer.settlement_type,'county':peer.district_raw,'population':peer.population,'distance_to_current_km':distance_km((donor['latitude'],donor['longitude']),(pp['latitude'],pp['longitude'])) if pp else None})
 edges.append({'from_source_record_id':a.source_record_id,'to_source_record_id':n.source_record_id,'relation':'same_place','decision_status':'checked_rule_accepted','case':case,'admission_rule':'Own coded currentQID explicit name/alias or literal im.-abbreviation plus raw native02 ownNP leaf and independent county; all compatible own-name competitors checked; census population unchanged','source_binding_proof':'accepted_source_bindings.csv.gz;actual_native02_raw_source_checks.csv.gz;all_native_name_competitors.csv.gz','population_boundary_comparability_asserted':False,'municipal_event_date':'UNKNOWN'})
 if not existing:
  pp={k:v for k,v in donor.items() if k!='point_ledger_path'};pp.update(target_source_record_id=a.source_record_id,coordinate_admission_status='reviewed_extension_rule_accepted',case=case,coordinate_binding_rule='Native source-bound own-name alias/current owncode-QID point with independent county and original native02 ownNP leaf',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,point_use_inference='modern_own_representative_point_on_native02_identity');points.append(pp)
 seen.add(a.source_record_id)
for name,data in [('accepted_identity_edge_delta.csv',edges),('accepted_point_use_delta.csv',points),('accepted_source_bindings.csv.gz',proof),('actual_native02_raw_source_checks.csv.gz',checks),('all_native_name_competitors.csv.gz',comp),('held_cases.csv',holds)]:pd.DataFrame(data).to_csv(O/name,index=False,compression='gzip' if name.endswith('.gz') else None)
s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();af=fm.finite_metrics(s)
outs=['accepted_identity_edge_delta.csv','accepted_point_use_delta.csv','accepted_source_bindings.csv.gz','actual_native02_raw_source_checks.csv.gz','all_native_name_competitors.csv.gz','held_cases.csv','native_alias_potential.csv']
r={'baseline_stage':34,'status':'Actual34 native missing02 alias CSV replay passed; ready future35 integration','accepted_cases':len(proof),'edges':len(edges),'point_uses':len(points),'holds':len(holds),'before':before,'after':after,'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':{'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']}},'input_pins':pins,'output_pins':{n:sha(O/n) for n in outs},'native_populations_quality_and_source_spelling_unchanged':True,'historical_census_coordinate_asserted':False}
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:r[k] for k in ['accepted_cases','edges','point_uses','holds','net_finite_all3_all_points']},ensure_ascii=False));print(pd.DataFrame(holds).to_string(index=False))
