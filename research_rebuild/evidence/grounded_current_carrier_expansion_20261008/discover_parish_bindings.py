from pathlib import Path
import sys,json,re,collections,math,ast,bisect
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;A=O.parent/'main_axis_residual_application63_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
from build_long_table import UnionFind
# Reuse the explicit lexical aliases from the closed geometry rule, not fuzzy names.
tree=ast.parse((O/'discover_closed_geometry.py').read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['nm','ty']],type_ignores=[]),'closed_literal_aliases','exec'))
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');V=O.parent/'main_axis_residual_registry_20261008/competitors/all_selected_native_competitors.parquet';RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');CP=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');c=duckdb.connect();f=c.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,population,is_additive_settlement_record,source_file,source_path,source_sheet,source_row,okato,oktmo from read_parquet(?)',[str(S)]).fetchdf();ef=c.execute('select source_record_id,effective_region_norm from read_parquet(?)',[str(V)]).fetchdf().set_index('source_record_id').effective_region_norm.to_dict();f['region_norm']=f.source_record_id.map(ef);p=c.execute('select target_source_record_id as source_record_id,latitude,longitude,point_origin_file,point_origin_sha256,point_origin_locator from read_parquet(?)',[str(A/'applied_point_snapshot.parquet')]).fetchdf().set_index('source_record_id').to_dict('index');raw=c.execute('select row_number()over() rn,object_level,object_name,oktmo,region,mun_upper,mun_lower,okato_dadata,oktmo_dadata,settlement_dadata,settlement_type_full_dadata,fias_level_dadata from read_parquet(?)',[str(RAW)]).fetchdf().astype(object).fillna('').set_index('rn');cl=c.execute('select * from read_parquet(?)',[str(CP)]).fetchdf();c.close();cs=pd.read_csv(A/'applied_component_snapshot.csv.gz',dtype=str,keep_default_na=False).set_index('source_record_id');members=cs.groupby('root').apply(lambda g:g.index.tolist(),include_groups=False).to_dict();rd=f.set_index('source_record_id').to_dict('index');remaining=set(pd.read_csv(A/'applied_remaining_primary.csv.gz',usecols=['source_record_id']).source_record_id);pins={str(q):sha(q) for q in [S,V,RAW,CP,A/'applied_point_snapshot.parquet',A/'applied_component_snapshot.csv.gz',A/'applied_remaining_primary.csv.gz',A/'application_receipt.json',O/'discover_closed_geometry.py']}
for q in [O/'accepted_current_point_delta.csv.gz',O.parent/'current_live_named_residual_sources_20261008/accepted_point_use_delta.csv.gz']:
 pins[str(q)]=sha(q)
 for z in pd.read_csv(q,dtype=str,keep_default_na=False).to_dict('records'):
  if z['target_source_record_id'] not in p:p[z['target_source_record_id']]=z
books={};context={};witness=[];headers={}
def parishkey(v):
 x=normalize(v);x=re.sub(r'[^а-яa-z0-9]+',' ',x);x=re.sub(r'\b(?:муниципальное|муниципальный|муниципальная|сельское|сельский|сельская|сельского|поселение|поселения|округ|округа|сельсовет|сельсовета|сельсоветы|волость|волости|администрация|администрации|поселковый|совет|сс)\b',' ',x);x=' '.join(x.split());x=re.sub(r'(?:ская|ское|ский|ского)$','ск',x);return x
parishpat=re.compile(r'\b(?:сельсовет(?:а|ы)?|волост(?:ь|и)|сельск(?:ий|ого) округ(?:а)?|сельская администрация|сельское поселение|поселковый совет|сс)\b')
def file(z):
 q=Path('/workspace/settlements-raw')/str(z['source_file']);return q if q.is_file() else Path(str(z['source_path']))
def oldcontext(sid):
 if sid in context:return context[sid]
 z=rd[sid];q=file(z);out={'source_record_id':sid,'year':int(z['census_year']),'parish_key':'','parish_role':'','parish_source_locator':'','parish_caption':'','parish_source_file':str(q),'parish_source_sha256':'','positive_context_anchor_source_IDs_json':'[]','bound_county_key':county_key(z['district_raw']) if int(z['census_year'])==2002 else ''}
 if q.suffix=='.xls' and q.is_file() and pd.notna(z['source_row']):
  if str(q) not in books:books[str(q)]=xlrd.open_workbook(str(q),on_demand=True);pins[str(q)]=sha(q)
  b=books[str(q)];sn=str(z['source_sheet']);sh=b.sheet_by_name(sn) if sn in b.sheet_names() else b.sheet_by_index(int(sn));rn=int(z['source_row'])-1
  hk=(str(q),sh.name)
  if hk not in headers:
   found=[]
   for i in range(sh.nrows):
    vals=sh.row_values(i);captions=[v for v in vals if isinstance(v,str) and len(v)<130 and parishpat.search(normalize(v)) and not normalize(v).startswith(('сельские населенные пункты','в том числе'))]
    if captions:found.append((i,captions[0]))
   headers[hk]=found
  hs=headers[hk];at=bisect.bisect_left(hs,(rn,''))-1
  if at>=0 and rn-hs[at][0]<=400:
   i,cap=hs[at];out.update(parish_key=parishkey(cap),parish_role='literal_previous_own_native_rural_subunit_caption',parish_source_locator=f'sheet={sh.name};row1based={i+1}',parish_caption=cap,parish_source_sha256=pins[str(q)])
 context[sid]=out;return out
# Native current parish may also be recovered from the independently typed/code-bound dated2009 classifier's parent rural unit.
cp=cl.drop_duplicates(['historical_okato','name','status']).copy();amb=set(cp.loc[cp.historical_okato.duplicated(keep=False),'historical_okato']);cp=cp[~cp.historical_okato.isin(amb)].set_index('historical_okato').to_dict('index');coded=duckdb.connect().execute('select target_source_record_id from read_parquet(?)',[str(Path('/workspace/settlements-work/grounded_current_carrier_expansion_20261008/source_positive_coded_current_candidates.parquet'))]).fetchdf();coded=set(coded.target_source_record_id);currentcontext={}
for sid,z in rd.items():
 if int(z['census_year'])!=2021:continue
 rr=raw.loc[int(sid.rsplit(':',1)[1])].to_dict();cap=str(rr['mun_lower']);key=parishkey(cap) if cap and parishpat.search(normalize(cap)) else '';proof={'source_record_id':sid,'parish_key':key,'parish_caption':cap,'parish_role':'literal_current_native_publisher_rural_subunit','parish_source_file':str(RAW),'parish_source_sha256':pins[str(RAW)],'parish_source_locator':f'parquet_1basedrow={sid.rsplit(":",1)[1]};mun_lower;object_name;own_OKTMO','bound_county_key':county_key(z['district_raw']),'dated_classifier_county_key':''}
 code=str(rr['okato_dadata']).removesuffix('.0');leaf=cp.get(code)
 if sid in coded and leaf and str(leaf['is_settlement_raw'])=='t' and nm(leaf['name'])==nm(z['settlement_name']):
  district=cp.get(code[:5]+'000')
  if district and 'район' in normalize(district['name']):proof['dated_classifier_county_key']=county_key(district['name'])
 if not key and sid in coded and leaf and str(leaf['is_settlement_raw'])=='t' and nm(leaf['name'])==nm(z['settlement_name']):
  parent=cp.get(code[:8]);header=cp.get(code[:8]+'000')
  if parent and str(parent['is_settlement_raw'])=='f' and parent.get('name') and (header and 'сельские населенные пункты' in normalize(header.get('name_full',''))):
   key=parishkey(parent['name']);proof.update(parish_key=key,parish_caption=parent['name'],parish_role='dated2009_actual_rural_classifier_parent_via_sourcepositive_current_own_FIAS_NP_OKATO',parish_source_file=str(CP),parish_source_sha256=pins[str(CP)],parish_source_locator=f'NPline={leaf["source_line_1based"]};NP_OKATO={code};parentline={parent["source_line_1based"]};parent_OKATO={code[:8]};headerline={header["source_line_1based"]}')
 currentcontext[sid]=proof
# Blank 2010 subunit requires three distinct already accepted full3 native source anchors, including both sides, in this exact source sheet within20 rows.
full3={root for root,ids in members.items() if len(ids)==3 and {int(rd[i]['census_year']) for i in ids}=={2002,2010,2021} and all(i in p and pd.notna(rd[i]['population']) for i in ids)};anchors=collections.defaultdict(list)
for root in full3:
 ids=members[root];cur=next(i for i in ids if int(rd[i]['census_year'])==2021);ctx=currentcontext[cur]
 if not ctx['parish_key']:continue
 for i in ids:
  zz=rd[i]
  if int(zz['census_year'])!=2021 and pd.notna(zz['source_row']):anchors[(zz['source_file'],str(zz['source_sheet']))].append((int(zz['source_row']),i,cur,ctx['parish_key'],ctx['bound_county_key']))
for av in anchors.values():av.sort()
def bound(sid):
 z=oldcontext(sid)
 if int(rd[sid]['census_year'])!=2010:return z
 ids=members[cs.loc[sid,'root']];olds=[i for i in ids if int(rd[i]['census_year'])==2002]
 if olds and z['parish_key']:
  oo=oldcontext(olds[0])
  if oo['parish_key']==z['parish_key'] and oo['bound_county_key']:z['bound_county_key']=oo['bound_county_key'];return z
 row=rd[sid]
 if not file(row).is_file() or file(row).suffix!='.xls':return z
 al=anchors[(row['source_file'],str(row['source_sheet']))];rnum=int(row['source_row']);left=bisect.bisect_left(al,(rnum-20,));right=bisect.bisect_right(al,(rnum+20,'\uffff'));aa=[v for v in al[left:right] if 0<abs(v[0]-rnum)<=20 and rd[v[1]]['region_norm']==row['region_norm'] and rd[v[2]]['region_norm']==row['region_norm']];aa.sort(key=lambda v:abs(v[0]-int(row['source_row'])));aa=aa[:3]
 if len(aa)==3 and len({nm(rd[v[1]]['settlement_name']) for v in aa})==3 and len({v[3] for v in aa})==1 and len({v[4] for v in aa})==1 and min(v[0] for v in aa)<int(row['source_row'])<max(v[0] for v in aa):
  z={**z,'parish_key':aa[0][3],'bound_county_key':aa[0][4],'parish_role':'three_distinct_accepted_full3_physical_NP_anchors_flanking_exact_native_row_within20','positive_context_anchor_source_IDs_json':json.dumps([{'source_record_id':v[1],'current_source_record_id':v[2],'physical_source_row':v[0],'offset':v[0]-int(row['source_row']),'parish_key':v[3]} for v in aa]),'parish_source_sha256':pins[str(file(row))]};context[sid]=z
 return z
native=collections.defaultdict(list);current=collections.defaultdict(list)
for sid,z in rd.items():
 if not z['is_additive_settlement_record']:continue
 k=(z['region_norm'],nm(z['settlement_name']))
 native[(int(z['census_year']),*k)].append(sid)
 if int(z['census_year'])==2021:current[k].append(sid)
uf=UnionFind(members);ys={r:{int(rd[i]['census_year']) for i in ids} for r,ids in members.items()};event=set(pd.read_csv(O.parent/'remaining_large_lifecycle_residual_20261008/accepted_direct_event_native_credit_union.csv',usecols=['source_record_id']).source_record_id)
for q in [A/'lifecycle_round2_accepted_source_UID_credit_union.csv']:
 if q.is_file():event.update(pd.read_csv(q,usecols=['source_record_id']).source_record_id);pins[str(q)]=sha(q)
seen=set();out=[];holds=[];rivals=[];counts=collections.Counter()
for sid in sorted(remaining,key=lambda i:-(float(rd[i]['population']) if pd.notna(rd[i]['population']) else 0)):
 z=rd[sid]
 if int(z['census_year']) not in [2002,2010]:continue
 oc=bound(sid);key=oc['parish_key']
 if not key:continue
 match=[cur for cur in current[(z['region_norm'],nm(z['settlement_name']))] if currentcontext[cur]['parish_key']==key and cur in p and oc['bound_county_key'] and oc['bound_county_key'] in [currentcontext[cur]['bound_county_key'],currentcontext[cur]['dated_classifier_county_key']]]
 if len(match)!=1:counts['parish-qualified current carrier not unique']+=1;continue
 cur=match[0];ar,br=uf.find(cs.loc[sid,'root']),uf.find(cs.loc[cur,'root'])
 if ar==br:continue
 if ys[ar]&ys[br]:continue
 ids=list(dict.fromkeys(members[ar]+members[br]));rr=[]
 for i in ids:
  if int(rd[i]['census_year'])==2021:continue
  scope=bound(i);ns=native[(int(rd[i]['census_year']),rd[i]['region_norm'],nm(rd[i]['settlement_name']))];comp=[];unknown=[]
  for other in ns:
   otherctx=bound(other)
   if otherctx['parish_key']==scope['parish_key'] and (not otherctx['bound_county_key'] or otherctx['bound_county_key']==scope['bound_county_key']):comp.append(other)
   elif not otherctx['parish_key'] and (not county_key(rd[other]['district_raw']) or not county_key(rd[i]['district_raw']) or county_key(rd[other]['district_raw'])==county_key(rd[i]['district_raw'])):unknown.append(other)
   rivals.append({'target_source_record_id':i,'rival_source_record_id':other,'rival_type':rd[other]['settlement_type'],'rival_population':rd[other]['population'],'rival_county':rd[other]['district_raw'],'rival_parish_key':otherctx['parish_key'],'rival_parish_role':otherctx['parish_role'],'rival_caption_locator':otherctx['parish_source_locator'],'rival_unresolved_samecounty':other in unknown})
  if not scope['parish_key'] or scope['parish_key']!=key or not scope['bound_county_key'] or scope['bound_county_key'] not in [currentcontext[cur]['bound_county_key'],currentcontext[cur]['dated_classifier_county_key']] or comp!=[i] or unknown:rr.append('actual same-year same-parish or unplaced samecounty native namesake unresolved')
 if any(i in event for i in ids):rr.append('published nonordinary lifecycle scope')
 if any(pd.isna(rd[i]['population']) for i in ids):rr.append('protected unknown native population')
 point=(float(p[cur]['latitude']),float(p[cur]['longitude']))
 if any(i in p and distance_km(point,(float(p[i]['latitude']),float(p[i]['longitude'])))>5 for i in ids):rr.append('actual accepted component point >5km from grounded current carrier')
 pair=tuple(sorted([sid,cur]))
 if pair in seen:continue
 seen.add(pair);record={'from_source_record_id':sid,'to_source_record_id':cur,'name':z['settlement_name'],'from_year':int(z['census_year']),'to_year':2021,'from_population':z['population'],'to_population':rd[cur]['population'],'region':z['region_norm'],'parish_key':key,'native_historical_parish_witness_json':json.dumps(oc,ensure_ascii=False),'native_current_parish_witness_json':json.dumps(currentcontext[cur],ensure_ascii=False),'component_source_ids_json':json.dumps(ids),'positive_binding_method':'literal native ownleaf/count + printed rural parish/direct current native codedNP subunit or dated coded classifier rural parent + complete allnative same-year named parish rivals, three original-source accepted anchors for blank2010','imported_candidate_old_coordinate_not_used_for_identity_or_historic_measurement':True}
 if rr:record['held_reason']='; '.join(sorted(set(rr)));holds.append(record);continue
 out.append(record);uf.union(ar,br);nr=uf.find(ar);members[nr]=ids;ys[nr]=ys[ar]|ys[br]
keep={i for q in out for i in json.loads(q['component_source_ids_json'])};witness=[z for i,z in context.items() if i in keep];rivals=[z for z in rivals if z['target_source_record_id'] in keep]
for name,x in [('parish_candidate_identity_pairs.csv.gz',out),('parish_actual_native_context_witnesses.csv.gz',witness),('parish_all_native_namesake_competitors.csv.gz',rivals),('parish_held_identity_pairs.csv.gz',holds)]:pd.DataFrame(x).drop_duplicates().to_csv(O/name,index=False,compression={'method':'gzip','mtime':0})
receipt={'baseline_stage':63,'candidate_generation_implies_admission':False,'candidate_pairs':len(out),'held_pairs':len(holds),'outcomes':dict(counts),'input_pins':pins,'output_pins':{q.name:sha(q) for q in O.glob('parish*.csv.gz')}};(O/'parish_candidate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
