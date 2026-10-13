import pandas as pd,json,gzip,hashlib,shutil,pathlib
P=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/over500_south_remaining_points_20261009');D=pathlib.Path('/dev/shm/over500-20261009/south_osm');R=pd.read_csv('/dev/shm/over500-20261009/south_remaining.csv').fillna('');W=pd.read_csv('/workspace/russian-settlements-research/research_rebuild/evidence/over500_south_wiki_sources_20261009/supplement3_cached_own_article_candidates.csv.gz').fillna('');O=pd.read_csv(D/'candidates.csv').fillna('');points=[];witness=[]
def h(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def sid(name):
 z=R[R.settlement_name==name];assert len(z)==1,(name,len(z));return z.iloc[0].source_record_id
def add(name,kind,selector,note):
 u=sid(name);r=R[R.source_record_id==u].iloc[0]
 if kind=='wiki':
  z=W[(W.source_record_id==u)&(W.article_title==selector)]
  if z.empty:
   z=pd.read_csv('/workspace/russian-settlements-research/research_rebuild/evidence/over500_south_wiki_sources_20261009/priority_article_coordinate_candidates.csv.gz');z=z[z.article_title==selector]
  q=z.iloc[0];origin=q.capture;loc=q.get("source_locator",f"pageid={q.pageid};revid={q.revid};prop=coordinates");lat=q.latitude;lon=q.longitude;cs='ruwiki:pageid='+str(int(q.pageid));sha=q.capture_sha256;own=q.article_title
 else:
  typ,oid=selector;q=O[(O.source_record_id==u)&(O.osm_type==typ)&(O.osm_id==oid)].iloc[0];raw=D/f'object_{typ}_{oid}.json.gz';obj=json.load(gzip.open(raw))['body']['elements'][0];assert obj['tags'].get('place') in ['village','hamlet','suburb','neighbourhood','locality','town'];own=obj['tags']['name'];origin=q.capture;sha=q.capture_sha256;loc=f'json.body[osm_type={typ};osm_id={oid}];lat,lon';lat=q.latitude;lon=q.longitude;cs=f'OSM:{typ}:{oid}:version={obj["version"]}';dest=P/raw.name;shutil.copy(raw,dest);witness.append(dict(target_source_record_id=u,object_file=str(dest),object_sha256=h(dest),object_version=obj['version'],object_tags=json.dumps(obj['tags'],ensure_ascii=False)))
 assert lat!='' and lon!='';points.append(dict(target_source_record_id=u,coordinate_source_record_id=cs,latitude=lat,longitude=lon,coordinate_admission_status='reviewed_extension_rule_accepted',admission_rule='source_bound_own_locality_literal_or_explicit_alias_with_native_county_context',point_origin_kind='own_locality_Wikipedia_primary_coordinate_claim' if kind=='wiki' else 'OSM_own_place_node_or_settlement_polygon_Nominatim_representative',point_origin_file=origin,point_origin_sha256=sha,point_origin_locator=loc,point_temporal_interpretation='Own locality representative reused retrospectively; census date measurement and census boundary equivalence not asserted',direct_historical_coordinate_measurement=False,boundary_comparability_asserted=False,native_code_binding_asserted=False,own_article_title=own,source_county=r.district_raw,source_binding_note=note))
add('Буденного','osm',('relation',7864194),'Exact named own former locality suburb in source Voronezh city; no receiving city point projection')
add('1-го отделения совхоза "Михайловский"','wiki','Михайловский (Панинский район)','Own article explicit former first department label and Paninsky; fifth department OSM rival excluded')
add('1-го отделения племзавода "Тойда"','osm',('node',1400066064),'First ordinal preserved; source Paninsky and own native Тойда 1-я; unnumbered Тойда and second department excluded')
add('совхоза "Опыт"','osm',('way',461732266),'Nominatim own alt_name explicitly совхоза Опыт; source Podgorensky and own settlement feature')
add('Центральное отделение совхоза им. Мичурина','osm',('node',3858844573),'OSM old_name exact expanded имени label; native Michurinsky')
add('Шидиб','wiki','Шидиб (Сельсовет Шидибский)','Native source explicitly Шидибский сс; Мазадинский rival excluded; 2009 code82251870002')
add('Верхний Чегем','osm',('relation',9432622),'OSM own place=village admin_level10 old_name=Верхний Чегем; municipality redirect excluded; population/boundaries not equated')
add('Веселовское','osm',('way',642075413),'Nominatim own feature alias Веселовское and Mozdok/Веселовская source council; own village feature')
add('Головинская Варежка','osm',('relation',5273227),'Exact own suburb/former locality; native city Kamенка subordination header; no city coordinate use')
add('Охотничья','osm',('relation',2405854),'Own Станция-Охотничья hamlet and Ulyanovsky; railway facility/stop points excluded;2009 own73252820008')
add('Выры','wiki','Выры (посёлок станции)','Native station and Mainsky; own station settlement article/code73220820001; separate selo73220820005 excluded')
add('Гимова','wiki','Гимово','Own history former central estate имени Гимова, native Mainsky, unique consistent own name')
add('совхоза "Серп и Молот"','osm',('relation',5330763),'Exact estate designation under native Ермоловский сельсовет;2009 code56255854001; own village polygon')
add('Центральная усадьба совхоза "Надеждинский"','wiki','Центральная Усадьба совхоза «Надеждинский»','Exact native own name and Serdobsky source/county; own code56656425101')
add('совхоза "Маяк"','wiki','Маяк (Липецкая область)','Own unique Маяк Eletsky source Волчанский council; own code42621412101; descriptor совхоз transparent')
add('Юбилейный','wiki','Юбилейное (Дагестан)','Unique consistent own Kizlyarsky locality; source rural council+2009 code82227840001; gender form transparent; no name event date asserted')
add('Школьный','wiki','Школьное (Дагестан)','Unique consistent own Kizlyarsky locality;source rural council+2009 code82227840007; gender form transparent')
add('Гоцатль Малое','wiki','Гоцатль Малый','Unique qualified lesser Gotsatl locality in Khunzakh; greater village rival excluded; grammatical ending transparent')
add('Мущули','wiki','Мушули','Native Khunzakh unique consistent own Мушули; щ/ш spelling difference explicit; no dated rename assertion')
add('Бильгады','wiki','Бильгади','Native Derbent unique consistent own Бильгади; ы/и spelling difference explicit; no dated rename assertion')
# all source attempts remain transparent even where a feature cannot bind
pd.DataFrame(points).to_csv(P/'accepted_point_use_delta.csv',index=False);pd.DataFrame(witness).to_csv(P/'osm_own_feature_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0})
receipts=pd.read_csv(D/'receipts.csv').fillna('');disp=[]
for _,r in R.iterrows():
 u=r.source_record_id;a=[p for p in points if p['target_source_record_id']==u];qq=receipts[receipts.source_record_id==u];ww=W[W.source_record_id==u];oo=O[O.source_record_id==u];disp.append(dict(source_record_id=u,settlement_name=r.settlement_name,status='accepted_ownpoint' if a else 'source_binding_unresolved',point_specific_reason=a[0]['source_binding_note'] if a else 'Captured candidates do not yet establish unique own settlement binding; finer native context or own alternate-name evidence required',wiki_captured_candidate_rows=len(ww),osm_captured_candidate_rows=len(oo),osm_queries=json.dumps(qq.to_dict('records'),ensure_ascii=False),native_source_witness='native_source_witnesses.csv.gz',population_unchanged=True,temporal_route_gap_not_used_as_point_block=True))
pd.DataFrame(disp).to_csv(P/'point_only_dispositions.csv.gz',index=False,compression={'method':'gzip','mtime':0})
pd.DataFrame(columns=['left_source_record_id','right_source_record_id','edge_type','decision_status','admission_rule']).to_csv(P/'accepted_identity_edge_delta.csv',index=False)
manifest={str(p):h(p) for p in P.iterdir() if p.is_file()};(P/'hash_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print('accepted',len(points),'remaining',len(R)-len(points))
