import sys,json,collections,re,importlib.util,math
from pathlib import Path
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));sys.path.insert(0,str(R/'research_rebuild/evidence/native2010_remaining_county_rule_mass_20261008'))
from current_chain_state_20261007 import sha,normalize,distance_km
from scan import cn,nm,fm
sp=importlib.util.spec_from_file_location('snapshot56',O/'frozen_working_state56.py');state=importlib.util.module_from_spec(sp);sp.loader.exec_module(state);s=state.load(56);before=s.metrics();bf=fm.finite(s);protected=s.obs[['source_record_id','population','population_value_quality','settlement_name','settlement_type']].copy();pins={str(p):sha(p) for p in [*s.inputs,O/'frozen_working_state56.py']};SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');pins[str(SEL)]=sha(SEL);c=duckdb.connect();meta=c.execute('select source_record_id,source_sheet,source_row,source_name_raw from read_parquet(?)',[str(SEL)]).fetchdf().set_index('source_record_id');CL=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');cl=c.execute('select * from read_parquet(?)',[str(CL)]).fetchdf();pins[str(CL)]=sha(CL);RAW21=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');roster=c.execute('select row_number() over() as rn,object_level,object_name,region,mun_upper,mun_lower,oktmo,population from read_parquet(?)',[str(RAW21)]).fetchdf();pins[str(RAW21)]=sha(RAW21);c.close();books={};raw=[];rivals=[];proof=[];holds=[];edges=[];points=[]
def nn(v):return ' '.join(re.sub('[^а-яa-z0-9]+',' ',re.sub(r'^(?:поселок|посёлок|село|деревня|хутор|город|пгт|станица|аул)\s+','',normalize(v))).split())
def labelcounty(sh,rn):
 for k in range(rn,-1,-1):
  for v in sh.row_values(k):
   if isinstance(v,str) and re.search(r'\bрайон(?:а)?\b',normalize(v)):
    key=normalize(v).split('район')[0];key=re.sub(r'ского\s*$','ский',key);return v,cn(key),k
 return '', '', -1
def rawcheck(sid):
 r=s.by_id.loc[sid];p=Path('/workspace/settlements-raw')/r.source_file
 if not p.exists():p=Path(str(r.source_path))
 if not p.is_file() and Path(str(r.source_file)).name==RAW21.name:p=RAW21
 if not p.is_file():return None
 pins[str(p)]=sha(p);m=meta.loc[sid]
 if p.suffix!='.xls':return {'source_record_id':sid,'source_file':str(p),'source_sha256':pins[str(p)],'protected_population':r.population,'protected_quality':r.population_value_quality,'source_locator':r.source_locator,'own_native_source_status':'existing_accepted_selected_own_NP_reference'}
 if p not in books:books[p]=xlrd.open_workbook(str(p),on_demand=True)
 b=books[p];sh=b.sheet_by_name(str(m.source_sheet)) if str(m.source_sheet) in b.sheet_names() else b.sheet_by_index(int(m.source_sheet));rn=int(m.source_row)-1;vals=sh.row_values(rn);pos=[i for i,v in enumerate(vals) if isinstance(v,str) and normalize(v)==normalize(m.source_name_raw)]+[i+1 for i in range(len(vals)-1) if isinstance(vals[i],str) and isinstance(vals[i+1],str) and normalize(vals[i]+' '+vals[i+1])==normalize(m.source_name_raw)]
 if not pos:return None
 nums=[v for v in vals[min(pos)+1:] if isinstance(v,(int,float)) or (isinstance(v,str) and re.fullmatch('[0-9]+',v.strip()))]
 if not any(float(v)==r.population for v in nums):return None
 hc,hkey,hr=labelcounty(sh,rn);expected=cn(r.district_raw);countyok=bool(expected and (hkey==expected or hkey.endswith(' '+expected) or (expected.endswith('ий') and hkey.endswith(expected[:-2]+'ого')))) if int(r.census_year)==2002 else True
 if not countyok:return None
 # Every literal NP namesake in the actual historic source sheet is retained; exact published county captions narrow before eligibility.
 ids=[]
 for k in range(sh.nrows):
  vv=sh.row_values(k)
  if not any(isinstance(v,str) and re.match(r'^\s*(?:пос[её]лок|деревня|село|хутор|город)\s+',v,re.I) and nn(v)==nn(r.settlement_name) for v in vv):continue
  cc,ck,cr=labelcounty(sh,k);same=ck==hkey;ids.append({'source_file':str(p),'sheet':sh.name,'row1based':k+1,'county_raw':cc,'county_key':ck,'same_source_county':same,'row_cells_json':json.dumps(vv,ensure_ascii=False)})
 rivals.extend({'target_native_source_record_id':sid,**z} for z in ids)
 if int(r.census_year)==2002 and len([z for z in ids if z['same_source_county']])!=1:return None
 return {'source_record_id':sid,'source_file':str(p),'source_sha256':pins[str(p)],'source_locator':f'sheet={sh.name};row1based={rn+1}','raw_own_label':m.source_name_raw,'raw_row_cells_json':json.dumps(vals,ensure_ascii=False),'protected_population':r.population,'protected_quality':r.population_value_quality,'actual_printed_county':hc,'actual_printed_county_locator':f'sheet={sh.name};row1based={hr+1}','actual_county_binding_passed':countyok}
for z in pd.read_csv(O/'full3_source_positive_candidates.csv.gz',keep_default_na=False).to_dict('records'):
 a=z['from_source_record_id'];b=z['to_source_record_id'];ids=json.loads(z['component_source_ids_json']);cp=s.point_rows[b];newchecks=[];reason=''
 for i in ids:
  rr=rawcheck(i)
  if not rr:reason='exact_actual_native_label_count_county_or_raw_namesake_hold';break
  newchecks.append(rr)
 gc=str(z['historical_okato_2009_raw']);pool=cl[cl.historical_okato.str.startswith(gc[:5])&cl.is_settlement_raw.eq('t')&cl.name.map(nn).eq(nn(s.by_id.loc[a,'settlement_name']))];rivals.extend({'target_native_source_record_id':a,'source_file':str(CL),'raw_classifier_own_code':r.historical_okato,'raw_classifier_name':r.name,'raw_classifier_type':r.status,'source_line_1based':r.source_line_1based} for r in pool.itertuples())
 if len(pool)!=1:reason='actual_full_classifier_county_roster_name_rival'
 target=s.by_id.loc[b];owncurrent=roster[roster.rn.eq(int(b.rsplit(':',1)[1]))].iloc[0];rp=roster[roster.object_level.eq('Населенный пункт')&roster.object_name.map(nn).eq(nn(target.settlement_name))];rp=rp[rp.mun_upper.map(cn).eq(cn(target.district_raw)) & rp.region.eq(owncurrent.region)];rivals.extend({'target_native_source_record_id':b,'source_file':str(RAW21),'raw_row1based':r.rn,'raw_NP_label':r.object_name,'raw_NP_code':str(r.oktmo),'raw_county':r.mun_upper,'raw_population':r.population} for r in rp.itertuples())
 if len(rp)!=1:reason='actual_full_current_county_roster_name_rival'
 if s.years[s.uf.find(a)]&s.years[s.uf.find(b)]:reason='sequential_occupied_year'
 if reason:holds.append({**z,'reason':reason});continue
 ids=list(dict.fromkeys(ids));rule='Exact native own NP leaf/count/county and all actual historic source/2009 classifier/current raw county rosters; independent own coded historic2011 and already admitted current own point within5km; accepted literal component names and source-bound county-caption aliases; compatible rural NP classes; no conflicting existing coordinates/code or events; population growth is a flag only; native counts and source quality preserved'
 edges.append({'from_source_record_id':a,'to_source_record_id':b,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':rule,'source_binding_proof':'accepted_native_source_witnesses.csv.gz;actual_native_source_checks.csv.gz;all_actual_source_roster_rivals.csv.gz','population_boundary_comparability_asserted':False});s.union(a,b)
 for i in ids:
  if i in s.point_rows:continue
  p={k:v for k,v in cp.items() if k!='point_ledger_path'};p.update(target_source_record_id=i,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_binding_rule=rule,historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,point_use_inference='own_current_representative_point_on_exact_native_code_county_name_and_historic_coded_point_continuity');points.append(p);s.point_rows[i]=dict(p)
 z.update(admission_status='checked_rule_accepted',population_extreme_growth_flag=max(z['old_population'],z['current_population'])>2*min(z['old_population'],z['current_population']) if min(z['old_population'],z['current_population'])>0 else max(z['old_population'],z['current_population'])>0,historical_boundary_comparability='UNKNOWN');proof.append(z);raw.extend(newchecks)
 for pp in [Path(cp['point_origin_file']),Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'),Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')]:pins[str(pp)]=sha(pp)
s.obs['root']=s.obs.source_record_id.map(s.uf.find);pd.testing.assert_frame_equal(protected,s.obs[protected.columns]);af=fm.finite(s);outputs=[]
for n,f,cols in [('accepted_identity_edge_delta.csv.gz',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('accepted_native_source_witnesses.csv.gz',proof,['source_record_id']),('actual_native_source_checks.csv.gz',raw,['source_record_id']),('all_actual_source_roster_rivals.csv.gz',rivals,['source_record_id']),('application_holds.csv.gz',holds,['source_record_id'])]:
 pd.DataFrame(f,columns=list(f[0]) if f else cols).to_csv(O/n,index=False,compression={'method':'gzip','mtime':0});outputs.append(n)
r={'baseline_stage':56,'accepted_cases':len(proof),'edges':len(edges),'point_uses':len(points),'before':before,'after':s.metrics(),'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':{'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-v for y,v in bf['populations_by_year'].items()}},'source_population_quality_names_types_unchanged':True,'historical_boundary_comparability':'UNKNOWN','input_pins':pins,'output_pins':{n:sha(O/n) for n in outputs}};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins','before','after']},ensure_ascii=False))
