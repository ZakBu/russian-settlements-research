from pathlib import Path
import pandas as pd,json,gzip,hashlib,re
O=Path(__file__).parent;E=O.parent;D=Path('/workspace/settlements-delivery/final-full-20261009')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(s):return re.sub(r'[^а-я0-9]','',s.lower().replace('ё','е'))
mp={
'подсобногохозяйствавоскресенское':'Посёлок подсобного хозяйства «Воскресенское»','ватутинки':'Ватутинки (посёлок)','московский':'Московский (город)','институтаполиомиелита':'Посёлок института полиомиелита','газопровода':'Газопровод (посёлок, Москва)','газопровод':'Газопровод (посёлок, Москва)','коммунарка':'Коммунарка (посёлок, Москва)','заводамосрентген':'Посёлок завода Мосрентген','марьино':'Марьино (посёлок, Москва)','филимонки':'Филимонки','марушкино':'Марушкино','совхозакрекшино':'Посёлок совхоза «Крёкшино»','яковлевское':'Яковлевское (деревня, Москва)','первомайское':'Первомайское (посёлок, Москва)','птичное':'Птичное (посёлок)','ремзавод':'Ремзавод (Наро-Фоминский район)','домаотдыхавороново':'Посёлок дома отдыха «Вороново»','лмс':'ЛМС','кленово':'Клёново (село, Москва)','краснаяпахра':'Красная Пахра (село)','шишкинлес':'Шишкин Лес (посёлок)','рогово':'Рогово (посёлок, Москва)','фабрикиим1мая':'Посёлок фабрики имени 1-го Мая','фабрикиимени1гомая':'Посёлок фабрики имени 1-го Мая','остафьево':'Остафьево (посёлок)','знамяоктября':'Знамя Октября','ерино':'Ерино (посёлок, Москва)','щапово':'Щапово (посёлок, Москва)','новогорск':'Новогорск','купавна':'Купавна (дачный посёлок)','болшево':'Болшево (Королёв)','первомайский':'Первомайский (Королёв)','текстильщик':'Текстильщик (Московская область)','никольскоархангельский':'Никольско-Архангельский','салтыковка':'Салтыковка (микрорайон Балашихи)','сходня':'Сходня','новоподрезково':'Новоподрезково (рабочий посёлок)','фирсановка':'Фирсановка','яковлево':'Яковлево (деревня, Москва)'}
pages={}
for f in ['moscow_exact_ownwiki_batch.json.gz','moscow_remaining_exact_ownwiki_batch.json.gz','moscow_final_two_exact_ownwiki_batch.json.gz']:
 p=O/f
 for page in json.load(gzip.open(p,'rt'))['query']['pages']:
  if page.get('coordinates'):pages[page['title']]=(page,p)
m=pd.read_csv(O/'classified_missing_ownpoint_inventory.csv',dtype=str,keep_default_na=False);m=m[m.region_norm.eq('московская')].copy();accepted=[];witness=[];holds=[]
for r in m.to_dict('records'):
 title=mp.get(norm(r['settlement_name']));source=pages.get(title)
 if not source:holds.append(dict(r,hold_reason='Own former locality point not yet sourced; do not reuse parent municipal/city anchor'));continue
 page,p=source;rev=page['revisions'][0];txt=rev['slots']['main']['content'];pt=next(x for x in page['coordinates'] if x.get('primary'))
 excerpt='\n'.join(x for x in txt.splitlines() if any(t in x.lower() for t in ['lat_deg','lon_deg','координат','ленинск','наро-фомин','подольск','ватутин','ремзавод','микрорайон','московск','посёлок','деревн']))[:6500]
 loc=f"query.pages[pageid={page['pageid']}].coordinates[primary=true]; own_article={page['title']}; revision={rev['revid']}"
 accepted.append(dict(target_source_record_id=r['source_record_id'],latitude=pt['lat'],longitude=pt['lon'],coordinate_admission_status='reviewed_rule_accepted',coordinate_source_record_id=f"ruwiki:pageid:{page['pageid']}",source_sha256=sha(p),source_locator=loc,point_origin_file=str(p),point_origin_sha256=sha(p),point_origin_locator=loc,point_origin_kind='own_exact_physical_locality_Wikipedia_primary_coordinate',admission_rule='Exact own typed named locality article; accepted existing historical native/sourceyear route preserved; municipality and city centroid excluded',retrospective_point_use_is_continuity_inference=True,historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,native_code_binding_asserted=False))
 witness.append(dict(target_source_record_id=r['source_record_id'],native_name=r['settlement_name'],native_type=r['settlement_type'],native_year=r['census_year'],native_population=r['population'],native_source_sha256=r['source_sha256'],native_source_locator=r['source_locator'],own_article=page['title'],pageid=page['pageid'],revision=rev['revid'],own_source_path=str(p),own_source_sha256=sha(p),exact_own_article_excerpt=excerpt,article_point_is_locality_not_parent=True,boundary_comparability='UNKNOWN',existing_temporal_route_reaudited=False))
# Explicit combined old published Vatutinki scope: own article assigns pos9581
# to the published village because the residential military pos has no NP status.
for a in accepted:
 if a['target_source_record_id'].endswith(':2652') or a['target_source_record_id'].endswith(':10446'):
  a['admission_rule']='Own named large military residential compound inside native published Vatutinki village scope: ownarticle explicitly says2002pos9581 counted undervillage. Tiny2005village57 remains separate;2010exactcomposition UNKNOWN; no parentpoint.'
  a['point_scope_interpretation']='published Vatutinki village scope includes named military residential pos; ownlargecompound representative, exacthistoricextent UNKNOWN'
for w in witness:
 if w['native_name']=='Ватутинки':
  page,_=pages['Ватутинки (посёлок)'];txt=page['revisions'][0]['slots']['main']['content']
  w['exact_own_article_excerpt']='\n'.join(x for x in txt.splitlines() if 'учтено в деревне' in x or 'население' in x or 'год переписи' in x or 'lat_deg' in x or 'lon_deg' in x)
# Historical named compound, representative manually located in mapped housing;
# modern neighborhood polygon is corroboration only, never a parent/city donor.
hold=next(r for r in holds if 'совхоза' in r['settlement_name'])
p=O/'Sovkhoz1May_N37_004_primary_map.jpg';loc='N37-004 terrain1985 edition1987; literal свх.им.1Мая beside own residential blocks southeastЩитниково/eastMKAD; image2800x3311; housingapprox pixel1865,1810; crop1700,1650,2200,2150; visualframegeoreference, uncertaintyapproximately300m includingSK42/WGS84 difference'
accepted.append(dict(target_source_record_id=hold['source_record_id'],latitude=55.814,longitude=37.847,coordinate_admission_status='reviewed_rule_accepted',coordinate_source_record_id='manual_primary_map:N37-004:own_sovkhoz1May_housing',source_sha256=sha(p),source_locator=loc,point_origin_file=str(p),point_origin_sha256=sha(p),point_origin_locator=loc,point_origin_kind='manually_georeferenced_primary_1985_named_own_residential_compound_approximate_representative',admission_rule='Literal ownformerfarm name and residential compound on historical primarytopographicmap. Exactoldnative name/county matches; currentretained1Mayneighborhoodcorroborates area only; no citycentroid or currentboundarytransfer.',retrospective_point_use_is_continuity_inference=True,historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,native_code_binding_asserted=False,point_scope_interpretation='Approximate ownhistoricalresidentialcompound representative; mappedmeasurement1985, censusday/centroid/exactstatboundaryUNKNOWN',coordinate_accuracy_meters_approximate=300))
witness.append(dict(target_source_record_id=hold['source_record_id'],native_name=hold['settlement_name'],native_type=hold['settlement_type'],native_year=hold['census_year'],native_population=hold['population'],native_source_sha256=hold['source_sha256'],native_source_locator=hold['source_locator'],own_article='PRIMARY_MAP_N37-004_own_svkh_im1May',own_source_path=str(p),own_source_sha256=sha(p),exact_own_article_excerpt=loc,article_point_is_locality_not_parent=True,boundary_comparability='UNKNOWN',existing_temporal_route_reaudited=False))
holds=[]
pd.DataFrame(accepted).to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(witness).to_csv(O/'Moscow_own_article_native_target_binding_witnesses.csv',index=False);pd.DataFrame(holds).to_csv(O/'Moscow_remaining_point_holds.csv',index=False)
print('READY',len(accepted),'HOLDS',[(r['settlement_name'],r['source_record_id']) for r in holds])
