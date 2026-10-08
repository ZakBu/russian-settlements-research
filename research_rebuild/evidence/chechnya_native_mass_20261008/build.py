import sys,json,re,bisect,difflib
from pathlib import Path
from collections import defaultdict
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km,sha
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(29);before=s.metrics();inputs={str(p):sha(p) for p in s.inputs};c=duckdb.connect();meta=c.execute('select source_record_id,source_sheet,source_row,source_name_raw from read_parquet(?)',[str(Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'))]).fetchdf().set_index('source_record_id').to_dict('index');D={};origin={}
for p in Path('/workspace/settlements-work/continuation_20261004/R4/residual_alias_fetch/raw_entity_batches').glob('*.json'):
 for q,z in json.load(open(p)).get('entities',{}).items():D[q]=z;origin[q]=p
reg=s.obs[s.obs.region_norm.eq('чеченская')].copy();curr=reg[reg.census_year.eq(2021)].to_dict('records');candidates=pd.read_csv(O/'population_context_candidates.csv').to_dict('records');books={};checks={};edges=[];points=[];witness=[];holds=[]
def n(x):return re.sub('[^а-яa-z0-9]','',normalize(x))
def county(x):return county_key(x).replace('шатоевский','шатойский')
def vals(z,prop):return [x.get('mainsnak',{}).get('datavalue',{}).get('value') for x in z.get('claims',{}).get(prop,[]) if x.get('rank')!='deprecated']
def dated(z,y):
 out=[]
 for x in z.get('claims',{}).get('P1082',[]):
  if x.get('rank')=='deprecated':continue
  yy=[q.get('datavalue',{}).get('value',{}).get('time','')[1:5] for q in x.get('qualifiers',{}).get('P585',[])]
  if str(y) in yy:
   try:out.append(float(x['mainsnak']['datavalue']['value']['amount']))
   except:pass
 return out
def literal(a):
 sid=a['source_record_id'];m=meta[sid];p=Path('/workspace/settlements-raw')/a['source_file'];
 if p not in books:books[p]=xlrd.open_workbook(str(p),on_demand=True)
 sh=books[p].sheet_by_name(str(m['source_sheet']));r=int(m['source_row']);v=sh.row_values(r-1);lab=[(i,x) for i,x in enumerate(v) if isinstance(x,str) and normalize(m['source_name_raw'])==normalize(x)];pop=[(i,x) for i,x in enumerate(v) if (isinstance(x,(int,float)) and x==a['population']) or (isinstance(x,str) and re.fullmatch(r'[0-9]+',x.strip()) and int(x.strip())==a['population'])]
 okay=len(lab)==1 and bool(pop)
 checks[sid]={'source_record_id':sid,'file':str(p),'sha256':sha(p),'sheet':sh.name,'row_1based':r,'raw_label':lab[0][1] if lab else '', 'selected_population':a['population'],'literal_label_and_population':okay,'raw_cells':json.dumps(v,ensure_ascii=False)}
 return okay
def emit(a,b,proof):
 sid,bid=a['source_record_id'],b['source_record_id'];ra,rb=s.uf.find(sid),s.uf.find(bid)
 if ra==rb:return
 if s.years[ra]&s.years[rb]:raise ValueError('Repeated year')
 s.union(sid,bid);edges.append({'from_source_record_id':sid,'to_source_record_id':bid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'own dated entity count + printed native name and county; or exact native label in independently bracketed source county','source_binding_proof':proof,'population_boundary_comparability_asserted':False})
 cp=s.point_rows[bid]
 if sid not in s.point_rows:
  p=dict(cp);p.update(target_source_record_id=sid,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_use_rule='own accepted current locality point retrospectively reused by explicit same-place continuity; not historical measurement',coordinate_temporal_relation='retrospective_continuity_inference',source_binding_proof=proof);points.append(p);s.point_rows[sid]=p
# Explicit reviewed orthographic pairs; lexical similarity is a candidate aid, not independent identity evidence.
for z in candidates:
 if z['ratio']<.75:holds.append({**z,'reason':'former_name_or_large_lexical_change_requires_own_history'});continue
 a=s.by_id.loc[z['old_id']].to_dict();b=s.by_id.loc[z['cur_id']].to_dict();q=z['qid'];entity=D[q];cp=s.point_rows.get(b['source_record_id']);co=county(a['district_raw']);bc=county(b['district_raw'])
 if co!=bc:holds.append({**z,'reason':'historical_current_county_change_requires_own_history'});continue
 # Enumerate all region candidates by explicit own dated count, name variant and county before full-chain filtering.
 allcomp=[x for x in candidates if x['old_id']==z['old_id'] and x['ratio']>=.75 and county(x['old_county'])==county(x['cur_county'])]
 if len(allcomp)!=1:holds.append({**z,'reason':'competing_current_own_entity'});continue
 rawcode=str(int(b['oktmo'])) if pd.notna(b['oktmo']) else '';codes=vals(entity,'P764');p625=vals(entity,'P625');coords=[(x['latitude'],x['longitude']) for x in p625 if isinstance(x,dict)]
 if rawcode not in codes or not cp or not any(distance_km((cp['latitude'],cp['longitude']),v)<=1 for v in coords):holds.append({**z,'reason':'entity_native_own_code_or_point_not_independently_bound'});continue
 if a['population'] not in dated(entity,2002):raise ValueError('2002 value lost')
 if not literal(a):holds.append({**z,'reason':'native2002_literal_failed'});continue
 if s.years[s.uf.find(a['source_record_id'])]&s.years[s.uf.find(b['source_record_id'])] and s.uf.find(a['source_record_id'])!=s.uf.find(b['source_record_id']):holds.append({**z,'reason':'repeated_actual_year'});continue
 proof=f"Cached {origin[q]} sha256 {sha(origin[q])} entity {q} revision {entity.get('lastrevid')}; exact own P764 {rawcode}; own P625 matches admitted current point; explicit2002 P1082={a['population']}; printed2002 county={a['district_raw']}; reviewed orthographic pair {a['settlement_name']} -> {b['settlement_name']}; source witness literal_source_checks.csv"
 witness.append({**z,'raw_entity_sha256':sha(origin[q]),'revision':entity.get('lastrevid'),'current_native_oktmo':rawcode,'binding':'exact own dated2002 count + independently code/point-bound current QID + printed county + reviewed orthographic pair','population_2010_from_entity_not_used':json.dumps(dated(entity,2010))})
 emit(a,b,proof)
# Freeze the resulting independently accepted 2002/current pairs before extending exact-label native2010 rows.
pairs=[]
for z in witness:
 a=s.by_id.loc[z['old_id']].to_dict();b=s.by_id.loc[z['cur_id']].to_dict();pairs.append((a,b))
f=reg[reg.census_year.eq(2010)].copy();f['row']=f.source_record_id.map(lambda sid:meta[sid]['source_row']);anchors=[]
for a in f.to_dict('records'):
 root=s.uf.find(a['source_record_id']);bs=[b for b in curr if s.uf.find(b['source_record_id'])==root]
 if len(bs)==1:anchors.append((int(a['row']),a,county(bs[0]['district_raw']),bs[0]['source_record_id']))
anchors.sort(key=lambda z:z[0]);nums=[z[0] for z in anchors];contexts={};ctxw=[]
for a in f.to_dict('records'):
 row=int(a['row']);lo=bisect.bisect_left(nums,row)-1;hi=bisect.bisect_right(nums,row)
 if lo>=0 and hi<len(anchors):
  lower,upper=anchors[lo],anchors[hi]
  if lower[2]==upper[2] and row-lower[0]<=20 and upper[0]-row<=20 and n(lower[1]['settlement_name'])!=n(upper[1]['settlement_name']):
   if all(literal(x) for x in [a,lower[1],upper[1]]):contexts[a['source_record_id']]=lower[2];ctxw.append({'source_record_id':a['source_record_id'],'county':lower[2],'lower2010':lower[1]['source_record_id'],'lower2021':lower[3],'upper2010':upper[1]['source_record_id'],'upper2021':upper[3],'lowerrow':lower[0],'targetrow':row,'upperrow':upper[0]})
for a,b in pairs:
 if 2010 in s.years[s.uf.find(a['source_record_id'])]:continue
 competitors=f[f.settlement_name.map(n).eq(n(a['settlement_name']))].to_dict('records');eligible=[x for x in competitors if contexts.get(x['source_record_id'])==county(a['district_raw'])]
 if len(eligible)!=1 or any(x['source_record_id'] not in contexts for x in competitors):continue
 mid=eligible[0]
 if s.years[s.uf.find(mid['source_record_id'])]&s.years[s.uf.find(b['source_record_id'])]:continue
 emit(mid,b,'Exact preserved2002/2010 own label plus two-sided native2010 source neighbors in historical county; county_context_witness.csv; literal_source_checks.csv; own2002/current proof in accepted_pair_witness.csv')
# Union coverage once, fixed29 replay; native values never altered.
pd.DataFrame(edges,columns=['from_source_record_id','to_source_record_id','relation','decision_status','admission_rule','source_binding_proof','population_boundary_comparability_asserted']).to_csv(O/'accepted_identity_edge_delta.csv',index=False)
pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False)
pd.DataFrame(witness).to_csv(O/'accepted_pair_witness.csv',index=False);pd.DataFrame(checks.values()).to_csv(O/'literal_source_checks.csv',index=False);pd.DataFrame(ctxw).to_csv(O/'county_context_witness.csv',index=False);pd.DataFrame(holds).to_csv(O/'holds.csv',index=False)
after=s.metrics();receipt={'stage':29,'before':before,'after':after,'marginal':{y:{'population':after[y]['covered_population']-before[y]['covered_population'],'rows':after[y]['covered_rows']-before[y]['covered_rows']} for y in before},'accepted_edges':len(edges),'new_points':len(points),'reviewed_pairs':len(witness),'input_hashes':inputs,'native_source_values_unchanged':True,'known_holds':['Komsomolskoe2010 combined-grain independent composition hold','2009 Chechnya classifier contains no locality rows;82-prefixed points explicitly excluded'],'network_stop':'Wikipedia API429; no further requests'};(O/'receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False));print(json.dumps({k:v for k,v in receipt.items() if k!='input_hashes'},ensure_ascii=False))
