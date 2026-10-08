from pathlib import Path
import sys,json,gzip,re,hashlib
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;E=R/'research_rebuild/evidence';C=E/'moscow_large_residual_actionable_20261008'
sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
s=load(26);credit=set();pins={str(p):sha(p) for p in s.inputs}
for _,g in s.obs.groupby('root',sort=False):
 if set(g.census_year)=={2002,2010,2021} and g.population.notna().all() and all(x in s.point_rows for x in g.source_record_id):credit.update(g.source_record_id)
for fn in ['qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_publisher_partition_members.csv']:
 p=E/'working_full_chain_20261007'/fn;pins[str(p)]=sha(p);credit.update(pd.read_csv(p,dtype=str).source_record_id)
# Explicit already accepted transferred scope, even when not yet included in report.
p=E/'complete_transferred_municipal_scope_application_20261008/accepted_native_scope_constituents.csv';pins[str(p)]=sha(p);credit.update(pd.read_csv(p,dtype=str).source_record_id)
residual=E/'working_full_chain_20261007/top100_final_mixed_residual_2002.csv';pins[str(residual)]=sha(residual);pd.read_csv(residual)
regional=R/'research_rebuild/work/moscow_large_residual_actionable_20261008/remaining_moscow_mixed_uncredited.csv';pd.read_csv(regional);pins[str(regional)]=sha(regional)
raw={2002:Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls'),2010:Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls')};frames={y:pd.read_excel(p,header=None) for y,p in raw.items()}
for p in list(raw.values())+[C/'municipal_entities.json.gz',C/'municipal_pages.json.gz']:pins[str(p)]=sha(p)
ents=json.load(gzip.open(C/'municipal_entities.json.gz','rt'))['entities'];pages={p.get('pageprops',{}).get('wikibase_item'):p for p in json.load(gzip.open(C/'municipal_pages.json.gz','rt'))['query']['pages'].values()}
cfg=[('moskovsky','Q462784',2681,list(range(2682,2692)),list(range(10380,10389)),'Complete2002published10NPcouncil includesDudkino45;2005municipality formedcity+8NP;2010published9NPscope. Nofixedmodernrosterprojection.'),('vnukovskoye','Q4373600',2598,list(range(2599,2614)),list(range(10410,10425)),'Complete2002/2010published15NPscope. 2011Izvarinskoyeschool mergedintoVnukovo andsanatorium14intoRasskazovka;2021municipalterritoryreportedseparately.'),('sosenskoye','Q4373611',2692,[n for n in range(2693,2708) if n!=2699],list(range(10477,10488)),'Complete2002published14NPcouncil includeslaterMosrentgen11813/Mamyri andYazovo scopes.2005municipality formed11NP fromoldcouncil;2010complete11NPscope. Wholepredecessorscope retained; boundariesdifferent/unknown.'),('schapovskoye','Q4373613',4735,list(range(4736,4754)),list(range(12300,12318)),'Complete2002published18NPcouncil and2010complete18NPmunicipalroster. Protectednative2010sum differsmunicipalclaim214; noallocation.')]
obs=[];members=[];points=[];controls=[];hist=[];excerpts=[];reopened=[]
for key,q,parent,r02,r10,note in cfg:
 scope='moscow_sourceyear_'+key;ent=ents[q];page=pages[q];text=page['revisions'][0]['slots']['main']['*'];revision=page['revisions'][0]['revid']
 claims={}
 for st in ent['claims'].get('P1082',[]):
  for dt in st.get('qualifiers',{}).get('P585',[]):
   v=dt.get('datavalue',{}).get('value',{});y=int(v.get('time','+0000')[1:5])
   if y in [2010,2021]:claims[y]=(st,v)
 assert set(claims)=={2010,2021}
 p625=ent['claims'].get('P625',[])
 if p625:
  assert len(p625)==1;st=p625[0];v=st['mainsnak']['datavalue']['value'];lat,lon,prec=v['latitude'],v['longitude'],v['precision'];pointloc=st['id'];pointfile=C/'municipal_entities.json.gz';origin='wikidata_own_municipal_P625'
 else:
  def dms(axis):return [int(re.search(r'\|'+axis+'_'+part+r'\s*=\s*(\d+)',text).group(1)) for part in ['deg','min','sec']]
  a,b=dms('lat'),dms('lon');lat=a[0]+a[1]/60+a[2]/3600;lon=b[0]+b[1]/60+b[2]/3600;prec=1/3600;pointloc=f'pageid{page["pageid"]}:revision{revision}:municipalinfoboxlat/lon_deg/min/sec';pointfile=C/'municipal_pages.json.gz';origin='own_municipal_article_explicit_infobox_DMS'
 points.append(dict(scope_id=scope,scope_grain='whole_sourceyear_municipal_or_predecessor_territory',coordinate_source_record_id=q,municipal_entity_label=ent['labels']['ru']['value'],latitude=lat,longitude=lon,source_declared_precision_degrees=prec,point_origin_file=str(pointfile),point_origin_sha256=sha(pointfile),point_origin_locator=pointloc,point_origin_kind=origin,point_temporal_interpretation='Modern municipal representative; boundary comparability unknown',individual_NP_point_uses_created=0,population_boundary_comparability_asserted=False))
 for y,rr in [(2002,r02),(2010,r10)]:
  sheet='Sheet1' if y==2002 else 'Data Sheet';col=2 if y==2002 else 4;labelcol=1 if y==2002 else 3
  for n in rr:
   sid=f'{y}:{raw[y].name}:{sheet}:{n}';rawpop=float(frames[y].iloc[n-1,col]);rawlabel=str(frames[y].iloc[n-1,labelcol]);selected=sid in s.by_id.index;alias=''
   if y==2010 and key=='moskovsky' and n==10380:
    sid='2010:pub-11-1-4.pdf:pdf_page_11:42';selected=True;alias='Officialselectedurban17366 retained; secondaryrawcity17363 is auxiliarysamewholecity, noextracredit'
   assert selected,(key,y,n)
   r=s.by_id.loc[sid];pop=float(r.population)
   if not alias:assert pop==rawpop
   members.append(dict(scope_id=scope,scope_grain='whole_sourceyear_municipal_or_predecessor_territory',year=y,source_record_id=sid,native_name=r.settlement_name,native_type=r.settlement_type,native_county=r.district_raw,native_population=pop,native_population_quality=r.population_value_quality,raw_source_path=str(raw[y]),raw_source_sha256=pins[str(raw[y])],raw_sheet=sheet,raw_row_1based=n,raw_label=rawlabel,raw_population_cell='C' if y==2002 else 'E',raw_population=rawpop,selected_native_source_ID=True,already_in_stage26_and_accepted_scope_union=sid in credit,new_native_population_if_scope_admitted=0 if sid in credit else pop,member_binding_rule='Wholeprinted2002parent/allchildren' if y==2002 else 'Contiguouscomplete2010municipalroster; literalpublishednames andhistoricallegalmemberchanges',selected_official_override_note=alias,point_assigned_to_individual_NP=False,own_NP_2021_count_asserted=False,is_exclusive_constituent_at_own_scope=True))
  gm=[m for m in members if m['scope_id']==scope and m['year']==y];rawsum=sum(m['raw_population'] for m in gm);sel=sum(m['native_population'] for m in gm)
  if y==2002:
   total=float(frames[y].iloc[parent-1,2]);assert total==rawsum;ctrl=total;loc=f'Sheet1!C{parent}:wholeprintedparent; all{len(rr)}childNPs'
  else:ctrl=float(claims[y][0]['mainsnak']['datavalue']['value']['amount']);loc=claims[y][0]['id']
  controls.append(dict(scope_id=scope,year=y,whole_published_observation_population=ctrl,raw_children_count=len(rr),raw_children_sum=rawsum,selected_children_sum=sel,raw_sum_minus_municipal_claim=rawsum-ctrl,selected_sum_minus_municipal_claim=sel-ctrl,complete_sourceyear_roster=True,raw_contiguous_bounds=f'{rr[0]}-{rr[-1]}',non_NP_continuation_rows_skipped='2699 ethniccontinuation' if key=='sosenskoye' and y==2002 else '',control_locator=loc,discrepancy_policy='Preserveoriginalselectedpopulation/quality andseparatewholepublishedmunicipaltotal; noallocation'))
  for n in ([parent]+rr if y==2002 else [rr[0]-1]+rr+[rr[-1]+1]):reopened.append(dict(scope_id=scope,year=y,raw_sheet=sheet,row_1based=n,raw_cells_json=json.dumps([None if pd.isna(z) else z for z in frames[y].iloc[n-1,:6].tolist()],ensure_ascii=False,default=lambda z:int(z))))
 for y in [2002,2010,2021]:
  if y==2002:pop=float(frames[y].iloc[parent-1,2]);quality='direct_published_whole_sourceyear_rural_council_total';popfile=raw[y];loc=f'Sheet1!C{parent}';dt='2002 census';dp='census_year';refs='';grain='whole2002publishedpredecessorruralcouncil'
  else:
   st,v=claims[y];pop=float(st['mainsnak']['datavalue']['value']['amount']);quality='secondary_explicit_census_referenced_municipal_total';popfile=C/'municipal_entities.json.gz';loc=st['id'];dt=v['time'];dp=v['precision'];refs=json.dumps(st.get('references',[]),ensure_ascii=False);grain='wholepublishedsourceyearmunicipalterritory';assert st.get('references')
  gm=[m for m in members if m['scope_id']==scope and m['year']==y]
  obs.append(dict(scope_id=scope,observation_id=f'{scope}:{y}',census_year=y,population=pop,observation_grain=grain,scope_kind='complete_sourceyear_municipal_predecessor_territory',settlement_name=ent['labels']['ru']['value'],settlement_type='municipal_territorial_scope_not_individual_NP',selected_source_record_id='',is_additive_settlement_record=False,national2021_credit_population=0,own_NP_series_asserted=False,same_place_edge_created=False,population_boundary_comparability_asserted=False,modern_boundary_harmonized=False,municipal_point_scope_id=scope,latitude=lat,longitude=lon,point_precision_source_degrees=prec,native_members_count=len(gm),native_constituent_sum=sum(m['native_population'] for m in gm) if gm else '',native_population_and_quality_preserved=True,municipal_entity=q,population_value_quality=quality,population_source_file=str(popfile),population_source_sha256=sha(popfile),population_source_locator=loc,population_date=dt,date_precision=dp,population_references_json=refs,scope_change_note=note,decision_status='candidate_qualified_complete_sourceyear_scope_root_review_pending'))
 section=re.search(r'^== (?:Насел[её]нные пункты|Состав поселения) ==\s*([\s\S]*?)(?=^== |\Z)',text,re.M)
 history='\n'.join(l for l in text.splitlines() if any(w in l for w in ['сельский округ','2005','2004','2011','2012','lat_deg','lat_min','lat_sec','lon_deg','lon_min','lon_sec']))
 excerpts.append(f'{q} {page["title"]} revision{revision}\n{section.group(0) if section else ""}\n{history}\nSOURCEYEAR NOTE: {note}')
 hist.append(dict(scope_id=scope,qid=q,article_revision=revision,whole_sourceyear_roster2002_count=len(r02),whole_sourceyear_roster2010_count=len(r10),boundary_comparability='unknown; notconstantmodernbounds',scope_change_note=note))
M=pd.DataFrame(members);assert M.source_record_id.nunique()==len(M);M.to_csv(O/'candidate_native_scope_constituents.csv',index=False)
pd.DataFrame(obs).to_csv(O/'candidate_scope_observations.csv',index=False);pd.DataFrame(points).to_csv(O/'candidate_municipal_representative_points.csv',index=False);pd.DataFrame(controls).to_csv(O/'source_controls.csv',index=False);pd.DataFrame(hist).to_csv(O/'sourceyear_scope_changes.csv',index=False);pd.DataFrame(reopened).to_csv(O/'actual_raw_reopened_rows.csv',index=False);(O/'legal_literal_rosters_and_scope_changes.txt').write_text('\n\n'.join(excerpts),encoding='utf8')
# Official urban population source genuinely reopened by pdftotext before generation.
p=Path('/workspace/settlements-raw/data/raw/2010_official_tom11/pub-11-1-4.pdf');pins[str(p)]=sha(p);txt=(O/'official2010_urban_reopened.txt').read_text();assert re.search(r'Московский3\).*15563\s+17366',txt)
pd.DataFrame([dict(source_record_id='2010:pub-11-1-4.pdf:pdf_page_11:42',source_path=str(p),source_sha256=sha(p),source_locator='pdfpage11:Московский3),17366',population=17366,secondary_raw_same_city_population=17363,secondaryraw_extra_credit=0)]).to_csv(O/'official_urban_override_witness.csv',index=False)
(O/'source_manifest.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2));net={str(y):int(g.new_native_population_if_scope_admitted.sum()) for y,g in M.groupby('year')};receipt=dict(status='candidate_complete_sourceyear_scope_root_review_pending',baseline_stage=26,scope_count=4,scope_observations=12,native_constituents=len(M),conditional_new_unique_native_population=net,national2021_new_credit=0,ordinary_edges=0,individual_point_assignments=0,own_NP_three_year_series=0,boundary_comparability_asserted=False,modern_boundary_harmonized=False,discrepancies_preserved=True,source_manifest_sha256=sha(O/'source_manifest.json'));(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt))
