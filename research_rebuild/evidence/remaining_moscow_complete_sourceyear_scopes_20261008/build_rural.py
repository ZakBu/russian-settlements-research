from pathlib import Path
import sys,json,gzip,re,hashlib
import pandas as pd
R=Path('/workspace/russian-settlements-research');D=Path(__file__).parent;E=D.parent
sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
s=load(39);print('loaded explicit baseline39',flush=True)
credit=set()
f=s.obs.assign(root=s.obs.source_record_id.map(s.uf.find),point=s.obs.source_record_id.isin(s.point_rows),finite=s.obs.population.notna());ag=f.groupby('root').agg(years=('census_year','nunique'),point=('point','all'),finite=('finite','all'));roots=set(ag.index[(ag.years==3)&ag.point&ag.finite]);credit.update(f[f.root.isin(roots)].source_record_id)
baseline_inputs={str(p):sha(p) for p in s.inputs}
for fn in ['qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_publisher_partition_members.csv','complete_territorial_scope_constituents.csv','direct_inclusion_transformation_path_native_credit_union.csv']:
 p=E/'working_full_chain_20261007'/fn
 if p.exists():
  t=pd.read_csv(p,keep_default_na=False);credit.update(t.source_record_id);baseline_inputs[str(p)]=sha(p)
for p in E.glob('*application_20261008/accepted_native_scope_constituents.csv'):credit.update(pd.read_csv(p,keep_default_na=False).source_record_id)
for p in E.glob('*application_20261008/accepted_constituent_credit_union.csv'):credit.update(pd.read_csv(p,keep_default_na=False).source_record_id)
raw={2002:Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls'),2010:Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls')};frames={y:pd.read_excel(p,header=None) for y,p in raw.items()};pins={str(p):sha(p) for p in raw.values()};inv=pd.read_csv(D/'all21_municipality_inventory.csv',keep_default_na=False);ents={};pages={};origin={}
for b,ef,pf in [(E/'moscow_large_residual_actionable_20261008','municipal_entities.json.gz','municipal_pages.json.gz'),(D,'missing_municipal_entities.json.gz','missing_municipal_pages.json.gz'),(D,'klenovskoye_entities.json.gz','klenovskoye_title_resolution_pages.json.gz')]:
 for q,e in json.load(gzip.open(b/ef,'rt'))['entities'].items():ents[q]=e;origin[q]=(b/ef,b/pf)
 for p in json.load(gzip.open(b/pf,'rt'))['query']['pages'].values():
  if p.get('pageprops',{}).get('wikibase_item'):pages[p['pageprops']['wikibase_item']]=p
cfg=[('voskresenskoye','Q4373597',2620,list(range(2621,2628)),list(range(10430,10440))),('voronovskoye','Q4373596',4535,list(range(4536,4559)),list(range(12104,12127))),('klenovskoye','Q4373602',4559,list(range(4560,4582)),list(range(12127,12149))),('novofyodorovskoye','Q4373609',3644,[n for n in range(3645,3685) if n not in [3660,3665]],list(range(11389,11414))),('pervomayskoye','Q4373607',3685,list(range(3686,3715)),list(range(11414,11442))),('rogovskoye','Q4373608',4662,list(range(4663,4684)),list(range(12237,12256)))]
obs=[];members=[];points=[];controls=[];hist=[];excerpts=[];reopened=[];baseline_members=[]
for key,q,parent,r02,r10 in cfg:
 scope='moscow_sourceyear_'+key;e=ents[q];p=pages[q];text=p['revisions'][0]['slots']['main']['*'];ef,pf=origin[q];pins[str(ef)]=sha(ef);pins[str(pf)]=sha(pf)
 claims={}
 for st in e['claims'].get('P1082',[]):
  for dt in st.get('qualifiers',{}).get('P585',[]):
   v=dt.get('datavalue',{}).get('value',{});y=int(v.get('time','+0000')[1:5])
   if y in [2010,2021]:claims[y]=(st,v)
 assert set(claims)=={2010,2021} and all(st.get('references') for st,v in claims.values())
 st=e['claims']['P625'][0];v=st['mainsnak']['datavalue']['value'];lat,lon,prec=v['latitude'],v['longitude'],v['precision']
 points.append(dict(scope_id=scope,scope_grain='whole_sourceyear_municipal_or_predecessor_territory',coordinate_source_record_id=q,municipal_entity_label=e['labels']['ru']['value'],latitude=lat,longitude=lon,source_declared_precision_degrees=prec,point_origin_file=str(ef),point_origin_sha256=sha(ef),point_origin_locator=st['id'],point_origin_kind='wikidata_own_municipal_P625',point_temporal_interpretation='Modern municipal representative; boundary comparability unknown',individual_NP_point_uses_created=0,population_boundary_comparability_asserted=False))
 note=f'Complete2002literal predecessor council {len(r02)}NPs versus complete2010published municipality {len(r10)}NPs; independently published whole census controls retained. Sourceyear composition changes explicit, never fixedmodernboundary projection. Unknown raw leaf counts not imputed. Modern municipal ownpoint is representative_scope only.'
 if key=='voskresenskoye':note+=' Original2010printed block has10leaves including proper Воскресенское absent nine-row legal village list; cached article separately lists it in2012official addressing appendix353-ПП. Complete raw sourceyear roster preserved, no deletion.'
 for y,rr in [(2002,r02),(2010,r10)]:
  sheet='Sheet1' if y==2002 else 'Data Sheet';col=2 if y==2002 else 4;labelcol=1 if y==2002 else 3
  for n in rr:
   sid=f'{y}:{raw[y].name}:{sheet}:{n}';cell=frames[y].iloc[n-1,col];pop=None if pd.isna(cell) else float(cell);label=str(frames[y].iloc[n-1,labelcol]);selected=sid in s.by_id.index
   assert label.strip(),(key,y,n)
   if selected:
    r=s.by_id.loc[sid];assert float(r.population)==pop
    name,typ,county,quality=r.settlement_name,r.settlement_type,r.district_raw,r.population_value_quality;nativepop=float(r.population);src=sid;gain=0 if sid in credit else nativepop
    baseline_members.append(dict(scope_id=scope,year=y,source_record_id=sid,source_population=nativepop,already_in_explicit_baseline39_union=sid in credit,new_native_population=gain))
   else:
    assert pop is None or pop==0,(key,y,n,pop)
    name,typ,county,quality,nativepop,src,gain=label,'','',('raw_count_blank_unknown_not_zero' if pop is None else 'actual_raw_zero_absent_selected_layer_nonadditive'),'','',0
   members.append(dict(scope_id=scope,scope_grain='whole_sourceyear_municipal_or_predecessor_territory',year=y,source_record_id=src,observed_raw_row_id=sid,native_name=name,native_type=typ,native_county=county,native_population=nativepop,native_population_quality=quality,raw_source_path=str(raw[y]),raw_source_sha256=pins[str(raw[y])],raw_sheet=sheet,raw_row_1based=n,raw_label=label,raw_population_cell='C' if y==2002 else 'E',raw_population='' if pop is None else pop,selected_native_source_ID=selected,already_in_stage26_and_accepted_scope_union=(sid in credit if selected else False),already_in_explicit_baseline39_union=(sid in credit if selected else False),new_native_population_if_scope_admitted=gain,member_binding_rule='Completeliteral2002sourceparent/allchildren' if y==2002 else 'Complete2010contiguousmunicipalroster; literalpublishednames plus explicit sourceyearcompositionchange',selected_official_override_note='',point_assigned_to_individual_NP=False,own_NP_2021_count_asserted=False,is_exclusive_constituent_at_own_scope=True))
  gm=[m for m in members if m['scope_id']==scope and m['year']==y];rawsum=sum(m['raw_population'] for m in gm if isinstance(m['raw_population'],(int,float)));native=sum(m['native_population'] for m in gm if isinstance(m['native_population'],(int,float)))
  if y==2002:
   total=float(frames[y].iloc[parent-1,2]);assert total==rawsum;loc=f'Sheet1!C{parent}:wholeprintedparent; all{len(rr)}childNPs'
  else:total=float(claims[y][0]['mainsnak']['datavalue']['value']['amount']);loc=claims[y][0]['id']
  controls.append(dict(scope_id=scope,year=y,whole_published_observation_population=total,raw_children_count=len(rr),raw_children_sum=rawsum,selected_children_sum=native,raw_count_unknown_rows=sum(m['native_population_quality']=='raw_count_blank_unknown_not_zero' for m in gm),raw_sum_minus_municipal_claim=rawsum-total,selected_sum_minus_municipal_claim=native-total,complete_sourceyear_roster=True,raw_contiguous_bounds=f'{rr[0]}-{rr[-1]}',non_NP_continuation_rows_skipped='3660/3665 ethniccontinuation' if key=='novofyodorovskoye' and y==2002 else '',control_locator=loc,discrepancy_policy='Known raw counts sum is diagnostic only if unknowncounts present; actualwhole municipal observation independent; noallocation/zeroimputation'))
  for n in sorted(set(([parent]+list(range(r02[0],r02[-1]+2))) if y==2002 else [r10[0]-1]+r10+[r10[-1]+1])):reopened.append(dict(scope_id=scope,year=y,raw_sheet=sheet,row_1based=n,raw_cells_json=json.dumps([None if pd.isna(z) else z for z in frames[y].iloc[n-1,:6].tolist()],ensure_ascii=False,default=lambda z:int(z))))
 for y in [2002,2010,2021]:
  if y==2002:pop=float(frames[y].iloc[parent-1,2]);quality='direct_published_whole_sourceyear_rural_council_total';popfile=raw[y];loc=f'Sheet1!C{parent}';dt='2002 census';dp='census_year';refs='';grain='whole2002publishedpredecessorruralcouncil'
  else:st,v=claims[y];pop=float(st['mainsnak']['datavalue']['value']['amount']);quality='secondary_explicit_census_referenced_municipal_total';popfile=ef;loc=st['id'];dt=v['time'];dp=v['precision'];refs=json.dumps(st['references'],ensure_ascii=False);grain='wholepublishedsourceyearmunicipalterritory'
  gm=[m for m in members if m['scope_id']==scope and m['year']==y]
  obs.append(dict(scope_id=scope,observation_id=f'{scope}:{y}',census_year=y,population=pop,observation_grain=grain,scope_kind='complete_sourceyear_municipal_predecessor_territory',settlement_name=e['labels']['ru']['value'],settlement_type='municipal_territorial_scope_not_individual_NP',selected_source_record_id='',is_additive_settlement_record=False,national2021_credit_population=0,own_NP_series_asserted=False,same_place_edge_created=False,population_boundary_comparability_asserted=False,modern_boundary_harmonized=False,municipal_point_scope_id=scope,latitude=lat,longitude=lon,point_precision_source_degrees=prec,native_members_count=len(gm),native_constituent_sum=sum(m['native_population'] for m in gm if isinstance(m['native_population'],(int,float))) if gm else '',native_population_and_quality_preserved=True,municipal_entity=q,population_value_quality=quality,population_source_file=str(popfile),population_source_sha256=sha(popfile),population_source_locator=loc,population_date=dt,date_precision=dp,population_references_json=refs,scope_change_note=note,decision_status='candidate_qualified_complete_sourceyear_scope_root_review_pending'))
 section=re.search(r'^== (?:Насел[её]нные пункты|Состав поселения) ==\s*([\s\S]*?)(?=^== |\Z)',text,re.M)
 history='\n'.join(l for l in text.splitlines() if any(w in l for w in ['сельский округ','2005','2004','2011','2012']))
 excerpts.append(f'{q} {p["title"]} revision{p["revisions"][0]["revid"]}\n{section.group(0) if section else ""}\n{history}\nSOURCEYEAR NOTE: {note}')
 hist.append(dict(scope_id=scope,qid=q,article_revision=p['revisions'][0]['revid'],whole_sourceyear_roster2002_count=len(r02),whole_sourceyear_roster2010_count=len(r10),boundary_comparability='unknown; notconstantmodernbounds',scope_change_note=note))
M=pd.DataFrame(members);assert M[M.selected_native_source_ID].source_record_id.is_unique
M.to_csv(D/'candidate_native_scope_constituents.csv',index=False);pd.DataFrame(obs).to_csv(D/'candidate_scope_observations.csv',index=False);pd.DataFrame(points).to_csv(D/'candidate_municipal_representative_points.csv',index=False);pd.DataFrame(controls).to_csv(D/'source_controls.csv',index=False);pd.DataFrame(hist).to_csv(D/'sourceyear_scope_changes.csv',index=False);pd.DataFrame(reopened).to_csv(D/'actual_raw_reopened_rows.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(baseline_members).to_csv(D/'explicit_baseline39_candidate_native_ID_exclusions.csv',index=False);(D/'legal_literal_rosters_and_scope_changes.txt.gz').write_bytes(gzip.compress('\n\n'.join(excerpts).encode(),mtime=0));(D/'source_manifest.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2));(D/'baseline39_input_context_hashes.json').write_text(json.dumps(dict(label='Historicalbaseline39diagnosticcontext_only_not_current_or_future_report_witness',input_hashes_at_generation=baseline_inputs),ensure_ascii=False,indent=2))
net={str(y):int(g.new_native_population_if_scope_admitted.sum()) for y,g in M.groupby('year')};receipt=dict(status='candidate_complete_sourceyear_scope_root_review_pending',baseline_stage=39,baseline39_label='Frozen candidate ID exclusion subset; notfuture45union witness',scope_count=6,scope_observations=18,native_constituents=int(M.selected_native_source_ID.sum()),complete_raw_members=len(M),auxiliary_unknown_count_members=int(M.native_population_quality.eq('raw_count_blank_unknown_not_zero').sum()),auxiliary_actual_zero_members=int(M.native_population_quality.eq('actual_raw_zero_absent_selected_layer_nonadditive').sum()),conditional_new_unique_native_population=net,national2021_new_credit=0,ordinary_edges=0,individual_point_assignments=0,own_NP_three_year_series=0,boundary_comparability_asserted=False,modern_boundary_harmonized=False,discrepancies_preserved=True,source_manifest_sha256=sha(D/'source_manifest.json'),outputs={p.name:sha(p) for p in D.iterdir() if p.suffix=='.csv' or p.name.endswith('.csv.gz')})
(D/'candidate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False));print(M.groupby(['scope_id','year']).new_native_population_if_scope_admitted.sum().to_string())
