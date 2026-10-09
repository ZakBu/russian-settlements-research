from pathlib import Path
import pandas as pd,json,gzip,hashlib,math,re
O=Path(__file__).parent;d=pd.read_parquet('/dev/shm/over500-moscow-after.parquet');p=pd.read_parquet('/dev/shm/over500-moscow-points.parquet').set_index('target_source_record_id');edges=pd.read_csv(O/'accepted_identity_edge_delta.csv').to_dict('records');pts=pd.read_csv(O/'accepted_point_use_delta.csv').to_dict('records');proof=[];rivals=[];holds=[];pgs={};sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
for f in O.glob('own_wikipedia_batch*.json.gz'):
 for pg in json.load(gzip.open(f,'rt'))['query']['pages'].values():
  if pg.get('coordinates'):pgs[pg['title']]=(pg,f)
parent={x:x for x in d.after_root.unique()}
def find(x):
 while parent[x]!=x:x=parent[x]
 return x
def dist(a,b):return 111*math.hypot(a[0]-b[0],(a[1]-b[1])*math.cos(math.radians(a[0])))
configs=[
 ('ДСК «Мичуринец»',['дск мичуринец'],'Ленинский район','Мичуринец','literal_native_name_punctuation'),
 ('Посёлок Минвнешторга',['минвнешторга'],'Ленинский район','579','literal_native_name_county'),
 ('Десна (деревня, Москва)',['десна'],'Ленинский район','Ленин','literal_native_name_county'),
 ('Сосенки (деревня, Москва)',['сосенки'],'Ленинский район','Сосенки','whole_region_unique_literal_native_name_type'),
 ('Румянцево (деревня, Москва)',['румянцево'],'Ленинский район','Румянцево','literal_native_name_county'),
 ('Мешково (деревня, Новомосковский административный округ)',['мешково'],'Ленинский район','Мешково','literal_native_name_county'),
 ('Кузнецово (деревня, Москва)',['кузнецово'],'Наро-Фоминский район','Кузнецово','literal_native_name_county'),
 ('Посёлок дорожно-ремонтного пункта-3',['дорожно ремонтного пункта 3'],'Подольский район','54','whole_region_unique_literal_native_name_type'),
 ('Шеметово (городской округ Коломна)',['шеметово'],'Коломенский район','Непецин','ownarticle_county_modern_point_disambiguation'),
 ('Зарайский',['зарайский','центральной усадьбы совхоза зарайский'],'Зарайский район','2003','explicit_ownarticle_former_name'),
 ('Здравница (Сергиево-Посадский городской округ)',['здравница','детского дома моосо'],'Сергиево-Посадский район','2005','explicit_ownarticle_former_name'),
 ('Возрождение (городской округ Коломна)',['возрождение','отделения возрождение'],'Коломенский район','Возрождение','literal_native_ownership_designator'),
 ('Нижнее Маслово',['нижнее маслово','нижне маслово'],'Луховицкий район','Маслово','literal_native_grammatical_linking_spelling'),
 ('Посёлок Раменской агрохимстанции (РАОС)',['раменской агрохимстанции','раменской агрохимстанции раос'],'Раменский район','РАОС','literal_native_parenthetical_abbreviation'),
 ('Посёлок совхоза «Орешково»',['совхоза орешково'],'Луховицкий район','2011','literal_native_name_county_prior_to_explicit_merger'),
]
for title,names,county,term,rule in configs:
 pg,f=pgs[title];txt=pg['revisions'][0]['slots']['main']['*'];assert term in txt,(title,term);co=pg['coordinates'][0];wp=(co['lat'],co['lon']); cand=d[d.name_norm.isin(names)].copy();rivals.extend(cand.assign(case=title).to_dict('records'))
 cand=cand[cand.derived_oldcounty.eq(county)|cand.derived_oldcounty.isna()]
 # Missing county is usable only with region-wide literal name/type uniqueness or own admitted modern point matching the specific county-qualified article.
 keep=[]
 for z in cand.itertuples():
  if z.derived_oldcounty==county:keep.append(z.source_record_id);continue
  same=d[d.census_year.eq(z.census_year)&d.name_norm.eq(z.name_norm)&d.type_norm.eq(z.type_norm)]
  if len(same)==1 and ('whole_region_unique'in rule or county in ['Коломенский район']):keep.append(z.source_record_id);continue
  if z.census_year==2021 and z.source_record_id in p.index and dist(wp,(p.loc[z.source_record_id].latitude,p.loc[z.source_record_id].longitude))<2:keep.append(z.source_record_id)
 cand=cand[cand.source_record_id.isin(keep)];roots={find(z)for z in cand.after_root};full=d[d.after_root.map(find).isin(roots)]
 if cand.census_year.duplicated().any()or full.census_year.duplicated().any()or len(cand)==0:holds.append(dict(case=title,reason='Same-year native competitor or accepted component collision',UIDs='|'.join(cand.source_record_id)));continue
 if any(dist(wp,(p.loc[s].latitude,p.loc[s].longitude))>5 for s in full.source_record_id if s in p.index):holds.append(dict(case=title,reason='Own article contradicts an existing accepted component point',UIDs='|'.join(full.source_record_id)));continue
 cur=cand.sort_values('census_year').iloc[-1];case='moscow_sourcebound_'+str(pg['pageid']);loc=f'pageid={pg["pageid"]};revision={pg["revisions"][0]["revid"]}'
 proof.append(dict(case=case,own_article_title=title,source_path=str(f),source_sha256=sha(f),source_locator=loc,source_binding_rule=rule,native_county=county,all_native_UIDs='|'.join(cand.source_record_id),literal_source_excerpt='\n'.join(l for l in txt.splitlines()if any(t in l for t in [term,'цифровой идентификатор','прежние имена',county.split()[0][:6]])),independent_ownarticle_latitude=wp[0],independent_ownarticle_longitude=wp[1],native_population_not_replaced=True))
 for z in cand.itertuples():
  if find(z.after_root)!=find(cur.after_root):
   edges.append(dict(from_source_record_id=z.source_record_id,to_source_record_id=cur.source_record_id,relation='same_place',decision_status='checked_rule_accepted',case=case,admission_rule=rule+'; literal original county or region-unique own name/type; county-qualified own article; no competing same-year native component',source_binding_proof=str(O/'ownarticle_native_binding_witnesses.csv')+';'+str(O/'sourcebound_all_native_rivals.csv.gz'),population_boundary_comparability_asserted=False,municipal_event_date='UNKNOWN'))
   parent[find(z.after_root)]=find(cur.after_root)
 for z in full.itertuples():
  if z.source_record_id not in p.index and z.source_record_id not in {x['target_source_record_id']for x in pts}:
   pts.append(dict(target_source_record_id=z.source_record_id,latitude=wp[0],longitude=wp[1],coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id='Wikipedia:page'+str(pg['pageid']),source_sha256=sha(f),source_locator=loc+':coordinates[0]',point_origin_file=str(f),point_origin_sha256=sha(f),point_origin_locator=loc+':coordinates[0]',point_origin_kind='own_Wikipedia_qualified_native_locality_representative_point',case=case,coordinate_binding_rule=rule+'; literal source own name/type and independent county, all same-name native rivals retained; own article coordinates',point_use_inference='own_modern_representative_point_on_source_bound_native_identity',population_boundary_comparability_asserted=False,historical_census_coordinate_asserted=False,secondary_population_not_substituted_for_native=True))
d.after_root=d.after_root.map(find);d.to_parquet('/dev/shm/over500-moscow-after-sourcebound.parquet',index=False);pd.DataFrame(edges).drop_duplicates(['from_source_record_id','to_source_record_id']).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(pts).drop_duplicates('target_source_record_id').to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(proof).to_csv(O/'ownarticle_native_binding_witnesses.csv',index=False);pd.DataFrame(rivals).to_csv(O/'sourcebound_all_native_rivals.csv.gz',index=False);pd.DataFrame(holds).to_csv(O/'sourcebound_holds.csv',index=False);print('totaledges',len(edges),'points',len(pts),'sourceboundcases',len(proof),'holds',holds)
