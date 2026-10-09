from pathlib import Path
import pandas as pd,json,gzip,math,re,xlrd
O=Path(__file__).parent;D=pd.read_pickle('/dev/shm/over500-20261009/east_enriched.pkl');R=pd.read_csv(O.parent/'assigned.csv').fillna('');by=D.set_index('source_record_id');P=pd.read_parquet('/dev/shm/over500-20261009/points_compact.parquet').fillna('');par={}
def find(a):
 if a not in par:par[a]=a
 if par[a]!=a:par[a]=find(par[a])
 return par[a]
prior=[O.parent]+[O.parent/f'subbatch{k}'for k in range(2,6)]
for z in prior:
 E=pd.read_csv(z/'accepted_identity_edge_delta.csv');P=pd.concat([P,pd.read_csv(z/'accepted_point_use_delta.csv').fillna('')],ignore_index=True)
 for e in E.itertuples():par[find(by.loc[e.from_source_record_id,'root'])]=find(by.loc[e.to_source_record_id,'root'])
D['root']=D.root.map(find);by=D.set_index('source_record_id',drop=False);P=P.drop_duplicates('target_source_record_id',keep='last').set_index('target_source_record_id');edge=[];point=[];w=[];di=[];seen=set();books={};roots={k:g for k,g in D.groupby('root')}
needed=set(R.source_record_id);neededroots=set(D[D.source_record_id.isin(needed)].root);targets=D[D.census_year.eq(2002)&D.root.isin(neededroots)]
for t in targets.itertuples():
 if any(x in t.name_norm for x in ['часть','и станция']):continue
 rawfile=Path('/workspace/settlements-raw')/t.source_file
 if not rawfile.exists()or rawfile.suffix!='.xls' or '1_TOM' in t.source_file:continue
 if str(rawfile)not in books:books[str(rawfile)]=xlrd.open_workbook(str(rawfile))
 b=books[str(rawfile)];shname=t.source_record_id.rsplit(':',2)[1];sh=b.sheet_by_name(shname);row=int(t.ord)-1;start=None;end=None
 for n in range(row-1,max(-1,row-150),-1):
  if re.search(r'сельсовет|сельская администрация|сельский округ|сельское поселение',str(sh.cell_value(n,0)),re.I):start=n;break
 if start is None:continue
 for n in range(row+1,min(sh.nrows,row+150)):
  if re.search(r'сельсовет|сельская администрация|сельский округ|сельское поселение| район\b',str(sh.cell_value(n,0)),re.I):end=n;break
 if end is None:continue
 block=D[D.census_year.eq(2002)&D.source_file.eq(t.source_file)&D.ord.gt(start+1)&D.ord.le(end)]
 if len(block[block.name_norm.eq(t.name_norm)])!=1:continue
 for yr in [2010,2021]:
  if yr in set(roots[t.root].census_year):continue
  peers=[]
  for x in block.itertuples():
   z=roots[x.root];z=z[z.census_year.eq(yr)]
   if len(z)==1:peers.append(z.iloc[0])
  if len(peers)<3:continue
  files=set(x.source_file for x in peers)
  if len(files)!=1:continue
  ords=[x.ord for x in peers];lo=min(ords);hi=max(ords)
  if hi-lo>60:continue
  cg=D[D.census_year.eq(yr)&D.region_norm.eq(t.region_norm)&D.name_norm.eq(t.name_norm)&D.type_norm.eq(t.type_norm)&D.source_file.eq(next(iter(files)))&D.ord.between(lo-2,hi+2)]
  cg=cg[cg.county.eq(t.county)|cg.county.eq('')|pd.Series(t.county=='',index=cg.index)]
  if len(cg)!=1:continue
  c=cg.iloc[0];g=pd.concat([roots[t.root],roots[c.root]]).drop_duplicates('source_record_id')
  if g.census_year.duplicated().any():continue
  donors=[P.loc[s]for s in g.source_record_id if s in P.index];coherent=True
  if not donors:continue
  a=donors[0]
  for p in donors[1:]:
   la,lo0=float(a.latitude),float(a.longitude);lat,lon=float(p.latitude),float(p.longitude);dist=6371*2*math.asin(min(1,math.sqrt(math.sin(math.radians(lat-la)/2)**2+math.cos(math.radians(la))*math.cos(math.radians(lat))*math.sin(math.radians(lon-lo0)/2)**2)))
   if dist>5:coherent=False
  if not coherent:continue
  pair=tuple(sorted([t.source_record_id,c.source_record_id]))
  if pair in seen:continue
  seen.add(pair);wid=len(w);w.append(dict(target_source_record_id=t.source_record_id,candidate_source_record_id=c.source_record_id,printed2002_council=str(sh.cell_value(start,0)),printed2002_council_row0=start,printed2002_next_scope_row0=end,native_source_file=str(rawfile),target_raw_cells=sh.row_values(row),sourceblock_members=block[['source_record_id','name_norm','type_norm','root']].to_dict('records'),already_accepted_named_sourceblock_peers=[dict(source_record_id=x.source_record_id,ordinal=x.ord,county=x.county)for x in peers],counterpart_source_peer_envelope=[min(ords),max(ords)],envelope_extension_rows=2,all_native_name_region_rivals=D[D.region_norm.eq(t.region_norm)&D.name_norm.eq(t.name_norm)].source_record_id.tolist(),interpretation='Own historical council leaf uniquely identified by same exact name/type in narrowly located native counterpart source block. At least3 distinct accepted own locality peers independently bind historical council context; source reorder preserved; native counts and quality unchanged.'))
  edge.append(dict(from_source_record_id=t.source_record_id,to_source_record_id=c.source_record_id,relation='same_place',decision_status='checked_rule_accepted',admission_method='printed_historical_council_block_minimum_three_accepted_named_peers_unique_counterpart_leaf',admission_rule='Unique own exact name/type within explicit printed2002 council block; at least3 independently accepted counterpart own named peers, counterpart envelope<=60source rows with only2boundary rows; full region rivals retained; no conflicting county, duplicated sourceyear, or >5km accepted-point contradiction.',population_boundary_comparability_asserted=False,evidence_file=str(O/'identity_point_witnesses.json.gz'),evidence_locator=f'[{wid}]'))
  for sid in g.source_record_id:
   if sid in P.index:continue
   point.append(dict(target_source_record_id=sid,**{k:a[k]for k in ['latitude','longitude','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind']},coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_binding_rule='printed_historical_council_block_minimum_three_accepted_named_peers_unique_counterpart_leaf',point_use_inference='Own representative locality point used retrospectively by admitted native council-context continuity; exact censusdate coordinate and boundarycomparability unknown.',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,external_provider_ID_binding_asserted=False,current_carrier_source_record_id=a.name))
  for sid in g.source_record_id:di.append(dict(source_record_id=sid,disposition='accepted_printed_historical_council_native_peer_context_continuity'))
with gzip.open(O/'identity_point_witnesses.json.gz','wt')as f:json.dump(w,f,ensure_ascii=False)
edgecols=['from_source_record_id','to_source_record_id','relation','decision_status','admission_method','admission_rule','population_boundary_comparability_asserted','evidence_file','evidence_locator'];pointcols=['target_source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_binding_rule','point_use_inference','historical_census_coordinate_asserted','population_boundary_comparability_asserted','external_provider_ID_binding_asserted','current_carrier_source_record_id'];pd.DataFrame(edge,columns=edgecols).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(point,columns=pointcols).drop_duplicates('target_source_record_id').to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(di).drop_duplicates('source_record_id').to_csv(O/'record_dispositions.csv',index=False);print(len(edge),len(point),len(w));print([(x['target_source_record_id'],x['candidate_source_record_id'])for x in w])
