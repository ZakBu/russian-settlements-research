#!/usr/bin/env python3
"""Dated physical shops and pickup points; no counts become attraction mass."""
from __future__ import annotations
import argparse, gzip, hashlib, json, re, sys, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
sys.path.insert(0,str(REPO/'scripts/sgrt_mass'))
from scripts.sgrt_mass.match import norm, normalize_name, normalize_region
from scripts.sgrt_mass.education import osm_temporal_status, osm_lifecycle_reason

WB_URL='https://static-basket-01.wbbasket.ru/vol0/data/all-poo-fr-v11.json'
YANDEX_WIDGET_URL='https://widget-pvz.dostavka.yandex.net/api/b2b/platform/pickup-points/list'
YANDEX_WIDGET_BODY={'type':'pickup_point','operator_ids':['market_l4g'],'is_post_office':False}
OSM_CATALOG_PATH='research/sgrt_word_completion_20261021/model_inputs_cycle07/institutional_relink477_v1/commerce/source_objects_relinked.parquet'
EARTH_KM=6371.0088
DAILY_GROCERY={'supermarket','convenience','general','food','grocery','minimarket','mini_market'}
FOOD_SPECIALIST={'bakery','butcher','greengrocer','dairy','fish','seafood','farm','cheese','deli','frozen_food'}
NEGATIVE={'no','vacant','closed','disused','abandoned','demolished','yes:closed'}
L0_SERVICES={'daily_grocery','parcel_pickup'}

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for b in iter(lambda:stream.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()

def tags_dict(value):
 if isinstance(value,dict):return value
 try:return json.loads(value) if isinstance(value,str) else {}
 except (ValueError,TypeError):return {}

def classify_osm(tags):
 """Positive service tags precede lexical brand clues; names alone prove nothing."""
 shop=str(tags.get('shop','')).casefold();amenity=str(tags.get('amenity','')).casefold()
 pickup=shop in {'outpost','parcel_locker'} or amenity in {'parcel_locker','parcel_pickup'} or str(tags.get('parcel_pickup','')).casefold()=='yes'
 if pickup:return 'parcel_pickup','explicit_pickup_or_locker_tag'
 if shop in DAILY_GROCERY:return 'daily_grocery','explicit_general_food_shop_tag'
 if shop in FOOD_SPECIALIST:return 'daily_food_specialist','explicit_specialist_food_shop_tag_not_full_grocery_assortment'
 if amenity=='marketplace':return 'marketplace_unspecified_assortment','marketplace_tag_assortment_unknown'
 if amenity=='post_office':return 'postal_service','post_office_tag_not_a_marketplace_operator_contract'
 if shop in {'mall','department_store'}:return 'shopping_centre','mall_or_department_store_tag'
 if shop and shop not in NEGATIVE:return 'comparison_retail','other_positive_shop_tag'
 return 'unclassified_commerce','no_positive_target_service_tag'

def operator_name(tags):
 explicit=tags.get('operator') or tags.get('brand')
 if explicit:return str(explicit)
 # A lexical clue is an operator hint ONLY after a positive pickup tag exists.
 if classify_osm(tags)[0]!='parcel_pickup':return None
 name=norm(tags.get('name',''))
 for pattern,label in [(r'\bozon\b|\bозон\b','Ozon'),(r'\bwildberries\b|\bвайлдберриз\b|\bвалберис\b','Wildberries'),(r'\bяндекс\b|\byandex\b','Yandex'),(r'\bcdek\b|\bсдэк\b','CDEK'),(r'\bpickpoint\b','PickPoint')]:
  if re.search(pattern,name):return label
 return None

def finite_point(lat,lon):
 return pd.notna(lat) and pd.notna(lon) and np.isfinite(float(lat)) and np.isfinite(float(lon)) and -90<=float(lat)<=90 and -180<=float(lon)<=180

def point_xyz(lat,lon):
 a,b=np.radians(np.asarray(lat,float)),np.radians(np.asarray(lon,float))
 return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])

def chord_km(chord):return 2*EARTH_KM*np.arcsin(np.clip(np.asarray(chord)/2,0,1))

def legacy_bridge(reference,legacy):
 r=reference[reference.source_record_id.notna()]
 b=legacy[legacy.root.notna()&legacy.source_record_id_2021.notna()].merge(r[['root','source_record_id','name','region','population_role']],left_on=['root','source_record_id_2021'],right_on=['root','source_record_id'],validate='one_to_one',suffixes=('_legacy','_census'))
 if not b.id.is_unique:raise ValueError('Ambiguous legacy bridge')
 return b.set_index('id')

def normalize_osm(objects,reference,legacy):
 bridge=legacy_bridge(reference,legacy);rows=[]
 for raw in objects.itertuples(index=False):
  t=tags_dict(raw.tags_json);service,basis=classify_osm(t)
  snapshot=raw.snapshot if pd.notna(raw.snapshot) else raw.source_snapshot
  snapshot=str(snapshot) if pd.notna(snapshot) else '2021-01-01'
  start=t.get('start_date') or raw.source_start_date;end=t.get('end_date') or raw.source_end_date
  temporal=osm_temporal_status(start,end,snapshot[:10])
  lifecycle=osm_lifecycle_reason(raw.tags_json)
  valid=finite_point(raw.lat,raw.lon)
  status='observed';reason='source_service_assertion_not_verified_current_operation'
  if service=='unclassified_commerce':status='excluded_service_type';reason=basis
  if not bool(raw.count_eligible):status='excluded_source_duplicate_or_conflict';reason=str(raw.recovery_status)
  if str(t.get('shop','')).casefold() in NEGATIVE:status='excluded_negative_shop';reason='explicit_negative_shop_tag'
  if lifecycle:status='excluded_lifecycle';reason=lifecycle
  if temporal in {'ended_before_snapshot','started_after_snapshot'}:status='excluded_temporal';reason=temporal
  if not valid:status='excluded_geometry';reason='invalid_or_missing_physical_point'
  sid=None;identity='physical_site_np_identity_unknown';legacy_id=raw.baseline_uid
  if pd.notna(legacy_id) and legacy_id in bridge.index and raw.link_status=='explicit_address_locality_unique_within5km':
   b=bridge.loc[legacy_id]
   if normalize_name(raw.source_address_locality)==normalize_name(b.name_census):
    sid=b.source_record_id;identity='explicit_locality_and_exact_legacy_census_bridge'
  canonical=raw.canonical_site_id if pd.notna(raw.canonical_site_id) else raw.site_id
  rows.append(dict(provider_id=str(raw.site_id),source_object_id=str(raw.site_id),canonical_source_site_id=str(canonical),
   source_record_id=sid,service_code=service,supply_status=status,eligibility_reason=reason,service_basis=basis,
   site_lat=raw.lat,site_lon=raw.lon,source_id='OSM_RUSSIA_20210101_COMMERCE',source_year=2021,
   source_snapshot=snapshot[:10],source_snapshot_literal=snapshot,observation_year=2021,source_year_basis='historical_osm_snapshot',
   source_name=raw.name,operator=operator_name(t),source_address_locality=raw.source_address_locality,
   activity_address=str(t.get('addr:full','')),source_region_literal=raw.source_address_state,
   np_identity_basis=identity,evidence_kind='mapped_positive_service_tag',location_precision='osm_representative_point',
   source_start_date=None if pd.isna(start) else str(start),source_end_date=None if pd.isna(end) else str(end),
   temporal_status=temporal,lifecycle_exclusion_reason=lifecycle or None,tags_json=json.dumps(t,ensure_ascii=False),
   actual_operational_status_checked=False,observed_flow=False,historical_supply_needs_current_confirmation=True,opening_hours=t.get('opening_hours'),
   default_external_seed_eligible=status=='observed',capacity_known=False,source_url='https://www.openstreetmap.org',source_license='ODbL-1.0'))
 d=pd.DataFrame(rows)
 # Same source canonical site/service is one supplier even when node/way/relation
 # witnesses overlap. The raw witnesses are kept in the normalized ledger.
 conflict=d[d.supply_status.eq('observed')].groupby(['canonical_source_site_id','service_code']).source_record_id.nunique()
 conflict=set(conflict[conflict.gt(1)].index)
 mask=pd.Series([(a,b) in conflict for a,b in zip(d.canonical_source_site_id,d.service_code)],index=d.index)
 d.loc[mask,'source_record_id']=None
 d.loc[mask,'np_identity_basis']='conflicting_strict_np_identities_for_same_physical_site'
 candidates=d[d.supply_status.eq('observed')].sort_values(['canonical_source_site_id','service_code','source_record_id','provider_id'],na_position='last')
 duplicates=candidates.duplicated(['canonical_source_site_id','service_code'],keep='first')
 d.loc[candidates.index[duplicates],'supply_status']='excluded_same_source_canonical_duplicate'
 d.loc[candidates.index[duplicates],'eligibility_reason']='same_canonical_site_same_service_same_snapshot'
 d['default_external_seed_eligible']=d.supply_status.eq('observed')
 return d

STREET_SPLIT=r'\b(?:улица|ул|проспект|пр кт|пркт|пр т|переулок|пер|шоссе|бульвар|бульв|б р|площадь|пл|проезд|набережная|наб|микрорайон|мкр|квартал|тракт|тупик|аллея|линия|дорога|автодорога)\b'
def address_head(address):return re.split(STREET_SPLIT,norm(address),maxsplit=1)[0]
def place_type_ok(address,name,reference_type):
 typ=norm(reference_type)
 rules=[(r'\b(?:село|с)\s+',{'село'}),(r'\b(?:город|г)\s+',{'город'}),(r'\b(?:деревня|д)\s+',{'деревня'})]
 for pre,allowed in rules:
  if re.search(pre+re.escape(name)+r'(?!\w)',address) and typ and typ not in allowed:return False
 return True

LOCALITY_TYPES=[('поселок городского типа','urban'),('городской поселок','urban'),('сельский поселок','settlement'),
 ('рабочий поселок','urban'),('дачный поселок','urban'),('курортный поселок','urban'),('железнодорожная станция','station'),
 ('город','city'),('гор','city'),('г','city'),('деревня','village'),('дер','village'),('д','village'),
 ('село','selo'),('с','selo'),('поселок','settlement'),('пос','settlement'),('п','settlement'),
 ('пгт','urban'),('рп','urban'),('гп','urban'),('дп','urban'),('хутор','khutor'),('х','khutor'),('станица','stanitsa'),('ст ца','stanitsa'),('стца','stanitsa'),('станция','station'),('аул','aul')]
ADMIN_COMPONENT=r'\b(?:область|обл|край|республика|респ|район|округ|муниципальный|муниципальное|р н|ао)\b'

def locality_clue(value,known_names):
 """A whole locality field/component; never a word found in a street."""
 raw=norm(value);body=raw;kind=None;explicit=False;typed_prefix=False
 for literal,category in LOCALITY_TYPES:
  if raw.startswith(literal+' '):body=raw[len(literal):].strip();kind=category;explicit=True;typed_prefix=True;break
 if not explicit and normalize_name(raw) not in known_names:
  for literal,category in LOCALITY_TYPES:
   if raw.endswith(' '+literal):body=raw[:-len(literal)].strip();kind=category;explicit=True;break
 return {'raw':raw,'name':normalize_name(body),'type':kind,'typed':explicit,'typed_prefix':typed_prefix}

def locality_type_compatible(kind,reference_type):
 typ=norm(reference_type)
 if not kind or not typ:return True
 if kind=='city':return typ=='город'
 if kind=='village':return typ=='деревня'
 if kind=='selo':return typ=='село'
 if kind=='khutor':return typ=='хутор'
 if kind=='stanitsa':return typ=='станица'
 if kind=='aul':return typ=='аул'
 if kind=='urban':return typ in {'пгт','рабочий поселок','поселок городского типа','городской поселок','дачный поселок','курортный поселок'}
 if kind=='station':return 'станц' in typ
 if kind=='settlement':return typ.startswith('поселок') or typ in {'пгт','рабочий поселок','сельский поселок'}
 return False

def locality_witnesses(point,known_names,region_names,city_names):
 structured_value=getattr(point,'source_address_locality',None)
 structured=locality_clue(structured_value,known_names) if pd.notna(structured_value) and str(structured_value).strip() else None
 parts=[];regions=set();street_started=False
 state=getattr(point,'source_region_literal',None)
 if pd.notna(state) and normalize_region(state) in region_names:regions.add(normalize_region(state))
 for literal in str(point.activity_address).split(','):
  raw=norm(literal)
  if not raw or raw in {'россия','российская федерация','рф'} or re.fullmatch(r'\d{6}',raw):continue
  clue=locality_clue(raw,known_names)
  # Administrative words and street names are excluded as whole components.
  # Keep a genuinely typed place such as "поселок Краснодарский".
  if re.search(ADMIN_COMPONENT,raw) and not clue['typed']:
   region=normalize_region(raw)
   if region in region_names:regions.add(region)
   continue
  street_match=re.search(STREET_SPLIT,raw)
  if street_match:
   # An explicit typed NP before the street can share its comma component:
   # "поселок Российский улица Мира". An untyped street prefix such as
   # "Московский тракт" is never extracted as a locality.
   street_tail=raw[street_match.end():].strip()
   house_tail=bool(re.match(r'^(?:дом|корпус|корп|строение|стр|владение|вл|литера|лит|помещение|пом|подъезд|этаж|офис|квартира|кв)(?:\b|\d)',street_tail))
   has_street_name=bool(re.match(r'^(?:(?:[а-я]\s+){0,2}[а-я][а-я-]{2,}|\d{1,4}\s*[а-я][а-я-]{2,})',street_tail)) and not house_tail
   if not street_started and clue['typed_prefix'] and has_street_name:
    before_street=re.split(STREET_SPLIT,raw,maxsplit=1)[0].strip()
    before_clue=locality_clue(before_street,known_names)
    if before_clue['typed_prefix'] and before_clue['name']:parts.append(before_clue)
   street_started=True;continue
  if street_started:continue
  if clue['name']:parts.append(clue)
 noncity=[p for p in parts if p['typed'] and p['type']!='city']
 typed=[p for p in parts if p['typed']]
 if noncity:
  # A source city may be an enclosing delivery city; a named, typed village
  # in the physical address is finer evidence. Conflicting rural fields stay
  # unresolved rather than selecting whichever literal happens to be longer.
  if structured and structured['name'] not in {p['name'] for p in noncity} and structured['name'] not in city_names:
   return [],regions,'conflicting_structured_and_typed_address_localities'
  return noncity,regions,'explicit_typed_address_locality'
 if structured:
  if typed and any(p['name']!=structured['name'] for p in typed):return [],regions,'conflicting_structured_and_typed_address_localities'
  if any(p['name'] in known_names and p['name']!=structured['name'] for p in parts):return [],regions,'conflicting_structured_and_address_localities'
  return [structured],regions,'explicit_structured_locality'
 if typed:return typed,regions,'explicit_typed_address_locality'
 return [p for p in parts if p['name'] in known_names],regions,'exact_free_address_locality_component'

def match_wb_addresses(points,reference,population_wide=None,max_km=10.):
 """Literal locality plus nearby accepted point, never nearest-only identity."""
 r=reference[reference.source_record_id.notna()&reference.ordinary_spatial_2021&reference.lat.notna()&reference.lon.notna()].copy().reset_index(drop=True)
 if population_wide is not None:
  types=population_wide[population_wide.source_record_id_2021.notna()].set_index('source_record_id_2021').settlement_type_2021
  if not types.index.is_unique:raise ValueError('Nonunique accepted population identities')
  r['reference_type']=r.source_record_id.map(types)
 elif 'settlement_type_2021' in r:r['reference_type']=r.settlement_type_2021
 else:r['reference_type']=None
 r['normalized_name']=r.name.map(normalize_name)
 region_names=set(reference.region_norm.dropna())
 tree=cKDTree(point_xyz(r.lat,r.lon));xyz=point_xyz(points.site_lat,points.site_lon)
 nearby=tree.query_ball_point(xyz,2*np.sin(max_km/(2*EARTH_KM)),workers=1)
 dist,idx=tree.query(xyz,k=1,workers=1);names=r.normalized_name.to_numpy()
 known_names=set(reference['name'].dropna().map(normalize_name))
 city_names=set(r.loc[r.reference_type.map(norm).eq('город'),'normalized_name'])|{'москва','санкт петербург','севастополь'}
 links=[]
 for k,(p,near) in enumerate(zip(points.itertuples(index=False),nearby)):
  candidate=[];conflicting=[];witnesses,explicit_regions,basis=locality_witnesses(p,known_names,region_names,city_names)
  foreign=bool(re.search(r'баренцбург|barentsburg|svalbard',norm(p.activity_address)))
  for i in near:
   name=names[i]
   if not name:continue
   matched=[]
   for clue in witnesses:
    exact=clue['name']==name
    # A typed place followed by a house number is still an explicit place:
    # "Посёлок Краснодарский 66к2" is not a street-name substring.
    house=not exact and clue['typed'] and clue['name'].startswith(name) and bool(re.fullmatch(re.escape(name)+r'\s*(?:(?:дом|д|корпус|корп|к)\s*)?\d.*',clue['name']))
    if exact or house:matched.append(clue)
   if not matched:continue
   if not all(locality_type_compatible(clue['type'],r.reference_type.iloc[i]) for clue in matched):conflicting.append(i);continue
   if explicit_regions and explicit_regions!={normalize_region(r.region.iloc[i])}:continue
   candidate.append(i)
  witness_conflict=False
  if len(candidate)==1:
   selected_name=names[candidate[0]]
   witness_conflict=any(not (clue['name']==selected_name or (clue['typed'] and re.fullmatch(re.escape(selected_name)+r'\s*(?:(?:дом|д|корпус|корп|к)\s*)?\d.*',clue['name']))) for clue in witnesses)
  sid=None;status='no_unique_literal_locality_and_coordinate';distance=None
  if foreign:status='known_foreign_in_provider_ru_section'
  elif basis.startswith('conflicting_'):status=basis
  elif witness_conflict:status='ambiguous_multiple_literal_locality_components'
  elif len(candidate)==1:
   i=candidate[0];sid=r.source_record_id.iloc[i];distance=float(chord_km(np.linalg.norm(xyz[k]-tree.data[i])))
   status='literal_locality_type_and_unique_coordinate_within10km'
  elif len(candidate)>1:status='ambiguous_literal_localities_within10km'
  elif conflicting:status='literal_place_type_conflict_not_identity'
  nearest=int(idx[k]);links.append(dict(source_record_id=sid,np_identity_basis=status,linked_distance_km=distance,
   np_identity_candidate_count=len(candidate),nearest_reference_source_record_id=r.source_record_id.iloc[nearest],
   nearest_reference_distance_km=float(chord_km(dist[k])),regional_context_proxy=r.region.iloc[nearest],
   regional_context_is_proxy=True,known_foreign_source_country_label_conflict=foreign,
   locality_witness_basis=basis,locality_witnesses_json=json.dumps(witnesses,ensure_ascii=False),
   matched_reference_name=r.name.iloc[candidate[0]] if sid is not None else None,
   matched_reference_type=r.reference_type.iloc[candidate[0]] if sid is not None else None,
   identity_is_nearest_only=False))
 return pd.DataFrame(links,index=points.index)

def normalize_wb(payload,reference,population_wide=None,snapshot='2026-10-24'):
 if isinstance(payload,list):ru=next(x['items'] for x in payload if x.get('country')=='ru')
 elif isinstance(payload,dict) and 'ru' in payload:ru=payload['ru']
 else:raise ValueError('Unrecognized WB country catalogue')
 data=[]
 for raw in ru:
  coords=raw.get('coordinates') or [None,None];focus=raw.get('typePoint') in [8,34]
  valid=len(coords)>=2 and finite_point(coords[0],coords[1]);status='observed' if focus and valid else 'excluded_uninterpreted_delivery_type' if valid else 'excluded_geometry'
  data.append(dict(provider_id='wb:'+str(raw['id']),source_object_id=str(raw['id']),canonical_source_site_id='wb:'+str(raw['id']),
   service_code='parcel_pickup' if focus else 'unspecified_delivery_point',supply_status=status,
   eligibility_reason='published_locator_types8_34_with_hours_and_fittingrooms' if focus else 'source_type_not_automatically_pickup',
   service_basis='official_public_locator_type_focus_not_all_delivery_types',site_lat=coords[0] if len(coords)>0 else None,site_lon=coords[1] if len(coords)>1 else None,
   source_id='WB_PUBLIC_MAP_'+snapshot.replace('-',''),source_year=int(snapshot[:4]),source_snapshot=snapshot,observation_year=None,
   source_year_basis='acquisition_date_source_observation_date_not_explicit',source_name=raw.get('name') or 'Wildberries',operator='Wildberries',activity_address=raw.get('address',''),
   source_region_literal=None,evidence_kind='provider_public_locator_record',location_precision='provider_published_coordinates',
   actual_operational_status_checked=False,observed_flow=False,opening_hours=raw.get('workTime'),capacity_known=False,
   source_type_literal=raw.get('typePoint'),source_status_literal=raw.get('status'),source_status_semantics_verified=False,
   default_external_seed_eligible=status=='observed',source_url=WB_URL,source_country_literal='ru',source_country_is_publisher_label_not_boundary_proof=True))
 d=pd.DataFrame(data)
 if d.provider_id.duplicated().any():raise ValueError('Duplicate WB public point IDs')
 valid=d.site_lat.between(-90,90)&d.site_lon.between(-180,180)
 links=match_wb_addresses(d.loc[valid],reference,population_wide)
 d=d.join(links)
 d.loc[d.known_foreign_source_country_label_conflict.fillna(False),'supply_status']='excluded_known_foreign_country_label_conflict'
 d['default_external_seed_eligible']=d.supply_status.eq('observed')
 return d

def add_geographic_context(sites,reference):
 selected=reference.analysis_origin if 'analysis_origin' in reference else reference.ordinary_spatial_2021
 r=reference[selected&reference.lat.notna()&reference.lon.notna()].copy().reset_index(drop=True)
 tree=cKDTree(point_xyz(r.lat,r.lon));d=sites.copy();valid=d.site_lat.between(-90,90)&d.site_lon.between(-180,180)
 distances,indices=tree.query(point_xyz(d.loc[valid,'site_lat'],d.loc[valid,'site_lon']),k=1,workers=1)
 for col in ['nearest_reference_source_record_id','nearest_reference_distance_km','regional_context_proxy']:
  if col not in d:d[col]=None
 rows=d.index[valid];d.loc[rows,'nearest_reference_source_record_id']=r.source_record_id.iloc[indices].to_numpy()
 d.loc[rows,'nearest_reference_distance_km']=chord_km(distances)
 d.loc[rows,'regional_context_proxy']=r.region.iloc[indices].to_numpy()
 d['regional_context_is_proxy']=True
 roles=reference[reference.source_record_id.notna()].set_index('source_record_id').population_role
 d['source_population_role']=d.source_record_id.map(roles).fillna('unknown_np_identity')
 d['strict_identity_observed']=d.source_record_id.notna()
 return d

def bind_explicit_city_contexts(sites,reference):
 """Bind an explicitly named federal territory, not nearest-city ownership.

 Population of the city context stays nonadditive; no number is copied to POI.
 Already identified ordinary localities have priority over a coarse city name.
 """
 cities=reference[reference.source_record_id.notna()&reference.region.isin(['москва','санкт петербург','севастополь'])].copy()
 if cities.empty:return sites
 def city_literal(value):
  text=normalize_name(value)
  return re.sub(r'^(?:город|г)\s+|\s+(?:город|г)$','',text).strip()
 known_localities={city_literal(value) for value in reference['name'].dropna()}
 city_or_unkeyed=reference.get('settlement_type_2021',pd.Series('',index=reference.index)).eq('город')|reference.source_record_id.isna()
 corpus_localities={city_literal(value) for value in reference.loc[city_or_unkeyed,'name'].dropna()}
 d=sites.copy();known_regions=set(reference.region_norm.dropna());contexts=[]
 for row in cities.itertuples(index=False):
  name=normalize_name(row.name)
  contexts.append((row.source_record_id,name,normalize_region(row.region),re.compile(r'(?<!\w)'+re.escape(name)+r'(?!\w)')))
 city_name_by_id={sid:name for sid,name,region,pattern in contexts}
 # A federal territorial context is not a precise owner for a separately
 # named known locality inside it. Preserve the physical shop and hold only
 # that coarse identity; an arbitrary microdistrict is not rejected.
 if 'tags_json' in d:
  suburbs=d.tags_json.map(lambda value:city_literal(tags_dict(value).get('addr:suburb')))
  finer=d.source_record_id.isin(city_name_by_id)&suburbs.isin(known_localities)&suburbs.ne(d.source_record_id.map(city_name_by_id))
  d.loc[finer,'source_record_id']=None
  d.loc[finer,'np_identity_basis']='held_known_finer_suburb_not_precise_federal_city_ownership'
 candidate_rows=d.source_record_id.isna()
 city_text=pd.Series(False,index=d.index)
 for column in ['activity_address','source_address_locality','tags_json']:
  if column in d:
   city_text |= d[column].fillna('').astype(str).str.contains(r'москва|санкт.{0,6}петербург|севастополь',case=False,regex=True)
 for idx,row in d[candidate_rows&city_text].iterrows():
  tags=tags_dict(row.get('tags_json'));head=address_head(row.get('activity_address',''))
  locality_values=[city_literal(v) for v in [row.get('source_address_locality'),tags.get('addr:city'),tags.get('addr:place')] if pd.notna(v)]
  locality_values=[value for value in locality_values if value]
  suburb=city_literal(tags.get('addr:suburb'))
  if suburb in known_localities and suburb:locality_values.append(suburb)
  states=[normalize_region(v) for v in [row.get('source_region_literal'),tags.get('addr:state')] if pd.notna(v)]
  explicit_regions=set(s for s in states if s in known_regions)
  for part in str(row.get('activity_address','')).split(','):
   if re.search(r'область|обл\.?\b|край|республика|респ\.?\b',part,flags=re.I):
    value=normalize_region(part)
    if value in known_regions:explicit_regions.add(value)
  candidates=[];held_reasons=[]
  for sid,name,region,pattern in contexts:
   # Provider widgets may call a whole delivery region "Moscow and Moscow
   # Oblast". That header never overrides an explicitly named village.
   explicit_locality=bool(locality_values) and set(locality_values)=={name}
   contradictory_locality=any(value and value!=name for value in locality_values)
   plain_head=head
   for _ in range(2):plain_head=re.sub(r'^(?:(?:россия|российская федерация|рф)|\d{6})\s*','',plain_head).strip()
   address_parts=[norm(part) for part in str(row.get('activity_address','')).split(',')]
   address_parts=[part for part in address_parts if part and part not in {'россия','российская федерация','рф'} and not re.fullmatch(r'\d{6}',part)]
   first_part=address_parts[0] if address_parts else ''
   first_part=re.sub(r'^\d{6}\s*','',first_part).strip()
   unambiguous_address=city_literal(plain_head)==name or city_literal(first_part)==name
   literal=explicit_locality or unambiguous_address
   if not literal:
    if pattern.search(head):held_reasons.append('regional_header_or_ambiguous_city_mention_not_locality')
    continue
   if contradictory_locality:
    held_reasons.append('contradictory_explicit_noncity_locality');continue
   bare_other_localities=[]
   for part in str(row.get('activity_address','')).split(','):
    normalized_part=norm(part)
    # A full street component is not a locality. In particular a reference
    # place named Pushkin does not turn Pushkinskaya Street into another NP.
    if re.search(STREET_SPLIT,normalized_part):break
    place_literal=city_literal(normalized_part)
    if place_literal not in known_localities:
     # Zelenograd uses corpus numbers as addresses. Arbitrary numbered names
     # such as "Suzdalskaya 12" may instead be streets without a type word.
     building=re.fullmatch(r'(.+?)\s+(?:корпус|корп|к)\s*\d.*',normalized_part)
     candidate=city_literal(building.group(1)) if building else ''
     place_literal=candidate if candidate in corpus_localities else ''
    if len(place_literal)>=3 and place_literal!=name and place_literal in known_localities and place_literal not in {'россия','российская федерация','рф'}:
     bare_other_localities.append(place_literal)
   if bare_other_localities:
    held_reasons.append('nested_known_locality_before_street');continue
   # A nested named settlement remains separate even when an enclosing city
   # is also present in an address field. No nearest-NP replacement is made.
   # Keep comma boundaries: the "г" in "Москва, г. Подольск" belongs to
   # Podolsk, whereas the suffix in the widget's "Москва г" belongs to Moscow.
   part_heads=[address_head(part) for part in str(row.get('activity_address','')).split(',')]
   other_place_head=' '.join('' if city_literal(part)==name else pattern.sub(' ',part) for part in part_heads)
   noncity_type=bool(re.search(r'\b(?:деревня|село|поселок|пгт|хутор|станица|аул|город)\b|\b(?:д|с|п|г)\s+[а-я][а-я-]{2,}\b|\b[а-я][а-я-]{2,}\s+(?:д|с|п|г)\b',other_place_head))
   if noncity_type:
    held_reasons.append('nested_explicit_noncity_place_type');continue
   if not place_type_ok(head,name,'город'):continue
   if explicit_regions and explicit_regions!={region}:continue
   candidates.append(sid)
  if len(candidates)==1:
   d.at[idx,'source_record_id']=candidates[0]
   d.at[idx,'np_identity_basis']='explicit_federal_city_locality_or_unambiguous_address_noncontradictory_context'
  elif held_reasons:d.at[idx,'np_identity_basis']='held_federal_city_'+ '|'.join(sorted(set(held_reasons)))
 d['identity_is_nonadditive_territorial_context']=d.source_record_id.isin(cities.source_record_id)
 return d

def np_offers(sites,accepted_statuses=('observed',)):
 eligible=sites[sites.supply_status.isin(accepted_statuses)&sites.source_record_id.notna()]
 rows=[]
 for (sid,code,snapshot),g in eligible.groupby(['source_record_id','service_code','source_snapshot'],sort=True):
  rows.append(dict(provider_id='commerce-np:'+str(sid)+'|'+code+'|'+snapshot,source_record_id=sid,service_code=code,
   supply_status='observed' if g.supply_status.eq('observed').all() else 'proxy',source_id=json.dumps(sorted(set(g.source_id))),source_year=int(g.source_year.iloc[0]),
   source_snapshot=snapshot,provider_ids_json=json.dumps(sorted(set(g.provider_id))),provider_records=len(g),
   capacity_known=False,observed_flow=False,default_external_seed_eligible=False,object_count_is_attraction_weight=False,np_identity_basis='source_explicit_locality_and_census_identity',
   source_year_not_assumed_population_year=True))
 return pd.DataFrame(rows)

def pickup_operator_code(value):
 text=norm(value)
 for expression,code in [(r'wildber|вайлдбер|валдбер|валбер|вайлбер','wildberries'),(r'\bozon\b|озон','ozon'),
                         (r'яндекс|yandex','yandex'),(r'сдэк|\bcdek\b','cdek'),(r'boxberry|боксберри','boxberry'),(r'pickpoint|пикпоинт','pickpoint')]:
  if re.search(expression,text):return code
 return None

def write_pickup_variants(sites,output):
 """Alternatives of ONE pickup channel, not additional independent functions."""
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 family=sites[sites.service_code.eq('parcel_pickup')&sites.supply_status.eq('observed')].copy()
 current=family[family.source_id.str.startswith('WB_PUBLIC_MAP_')&family.source_year.eq(2026)].copy()
 current['alternative_to_service_code']='parcel_pickup'
 current['service_code']='parcel_pickup_wildberries_current'
 current['counts_as_independent_service_channel']=False
 current['operator_compatibility_scope']='Wildberries_only_order_specific_rules_unknown'
 current['order_specific_eligibility_unknown']=True
 current['other_operator_can_replace_this_point_for_same_order']=False
 save(current,out/'sites_wb_current')
 offered=np_offers(current)
 offered['alternative_to_service_code']='parcel_pickup'
 offered['counts_as_independent_service_channel']=False
 save(offered,out/'supply_wb_current')
 operators=family.copy();operators['source_operator_literal']=operators.operator
 operators['operator_code']=operators.operator.map(pickup_operator_code)
 operators['alternative_to_service_code']='parcel_pickup'
 operators['counts_as_independent_service_channel']=False
 operators['operator_compatibility_unknown']=operators.operator_code.isna()
 operators['order_specific_eligibility_unknown']=True
 operators['other_operator_can_replace_this_point_for_same_order']=False
 operators.loc[operators.operator_code.isna(),'supply_status']='held_operator_compatibility_unknown'
 operators['service_code']='parcel_pickup_'+operators.operator_code.fillna('unknown_operator')
 save(operators,out/'operator_service_sites')
 op_offers=np_offers(operators)
 op_offers['alternative_to_service_code']='parcel_pickup'
 op_offers['counts_as_independent_service_channel']=False
 save(op_offers,out/'operator_specific_supply')
 summary={'current_wildberries_sites':len(current),'current_wildberries_identity_offers':len(offered),
  'family_means_any_pickup_option_not_interchangeable_order_fulfillment':True,
  'operator_variants_are_independent_functions':False,
  'operator_status_counts':operators.assign(operator_code=operators.operator_code.fillna('unknown_operator')).groupby(['operator_code','source_id'],dropna=False).size().rename('sites').reset_index().to_dict('records'),
  'fresh_wb_source_snapshot':sorted(current.source_snapshot.unique()),
  'zero_observed_ozon_points_implies_absent_network':False}
 (out/'pickup_variants_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 return summary

def write_grocery_host_variant(sites,output):
 """An explicit retailer-host assertion is a separate, weaker food scenario."""
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 if 'source_address_comment' not in sites:return {'retailer_host_assertions':0}
 comment=sites.source_address_comment.fillna('').map(norm)
 direct=comment.str.contains('касса в магазине',regex=False)&comment.str.contains(r'пятерочка|перекресток',regex=True)
 host=sites[sites.supply_status.eq('observed')&sites.provider_operator_id.eq('5post')&direct].copy()
 host['parent_service_code']='parcel_pickup_5post_current'
 host['alternative_to_service_code']='daily_grocery'
 host['service_code']='daily_grocery_current_retail_host'
 host['supply_status']='proxy'
 host['retailer_host_evidence']='explicit_source_comment_cashdesk_inside_named_Pyaterochka_or_Perekrestok'
 host['service_type_inferred_from_retailer_host']=True
 host['independent_store_inventory']=False
 host['counts_as_independent_service_channel']=False
 host['order_specific_eligibility_unknown']=False
 host['parcel_order_compatibility_not_applicable']=True
 host['operator_compatibility_scope']='not_applicable_to_store_purchase'
 host['retailer_host_brand']=np.where(host.source_address_comment.map(norm).str.contains('перекресток',regex=False),'Перекрёсток','Пятёрочка')
 save(host,out/'sites_grocery_current_host_proxy')
 offers=np_offers(host,accepted_statuses=('proxy',))
 offers['alternative_to_service_code']='daily_grocery';offers['counts_as_independent_service_channel']=False
 offers['independent_store_inventory']=False
 save(offers,out/'supply_grocery_current_host_proxy')
 result={'retailer_host_assertions':len(host),'identity_presence_records':len(offers),
  'retailer_name_without_explicit_store_comment_is_sufficient':False,'independent_store_inventory':False,
  'admitted_to_original_2021_grocery_baseline':False,'requires_explicit_proxy_acceptance':True}
 (out/'grocery_host_proxy_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 return result

def acquire_yandex_public_widget(output,snapshot='2026-10-24',expected_sha256=None,network_operator='market_l4g'):
 """Read the same anonymous public endpoint used by the official widget."""
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 request_headers={'User-Agent':'sgrt-research/1','Content-Type':'application/json'}
 if network_operator not in {'market_l4g','5post'}:raise ValueError('Unsupported public widget operator')
 request_body={**YANDEX_WIDGET_BODY,'operator_ids':[network_operator]}
 prefix='yandex' if network_operator=='market_l4g' else 'fivepost'
 req=urllib.request.Request(YANDEX_WIDGET_URL,data=json.dumps(request_body).encode(),headers=request_headers,method='POST')
 with urllib.request.urlopen(req,timeout=90) as response:
  body=response.read(150_000_000);status=response.status;content_type=response.headers.get('Content-Type')
 checksum=hashlib.sha256(body).hexdigest()
 if expected_sha256 and checksum!=expected_sha256:raise ValueError('Public Yandex source changed; use the pinned saved snapshot or store a separate dated observation')
 path=out/(prefix+'_public_widget_pickup_'+snapshot.replace('-','')+'.json.gz')
 if path.exists():
  with gzip.open(path,'rb') as old:previous=hashlib.sha256(old.read()).hexdigest()
  if previous!=checksum:raise ValueError('A different frozen operator snapshot already exists; use a separate observation directory')
 with gzip.GzipFile(str(path),'wb',mtime=0) as stream:stream.write(body)
 payload=json.loads(body)
 metadata={'source_id':('YANDEX' if network_operator=='market_l4g' else 'FIVEPOST')+'_PUBLIC_WIDGET_PICKUP_'+snapshot.replace('-',''),'url':YANDEX_WIDGET_URL,
  'method':'POST','request_body':request_body,'request_headers':request_headers,
  'acquisition_date':snapshot,'source_observation_date_not_explicit':True,
  'public_client_provenance':'https://widget-pvz.dostavka.yandex.net/widget.js?v=2',
  'no_authentication_headers_used':True,'http_status':status,'bytes':len(body),'content_type':content_type,
  'sha256':checksum,'gzip_sha256':digest(path),'gzip_bytes':path.stat().st_size,'point_count':len(payload.get('points',[]))}
 (out/(path.name+'.metadata.json')).write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
 return path,metadata

def normalize_yandex(payload,reference,population_wide=None,snapshot='2026-10-24',network_operator='market_l4g'):
 if not isinstance(payload,dict) or not isinstance(payload.get('points'),list):raise ValueError('Yandex public widget response has no points list')
 if network_operator not in {'market_l4g','5post'}:raise ValueError('Unsupported public widget operator')
 is_yandex=network_operator=='market_l4g'
 prefix='yandex' if is_yandex else '5post'
 service_code='parcel_pickup_yandex_current' if is_yandex else 'parcel_pickup_5post_current'
 source_prefix='YANDEX' if is_yandex else 'FIVEPOST'
 rows=[]
 for raw in payload['points']:
  pos=raw.get('position') or {};address=raw.get('address') or {};country=norm(address.get('country',''))
  active_date=raw.get('deactivation_date');status='observed';reason='provider_public_widget_customer_pickup'
  if raw.get('type')!='pickup_point':status='excluded_not_customer_pickup';reason='source_type_not_pickup_point'
  if raw.get('operator_id')!=network_operator:status='excluded_other_operator';reason='source_operator_not_requested_yandex_network'
  if not country:status='held_source_country_unknown';reason='source_country_missing_not_assumed_russia'
  elif country not in {'россия','russia','ru','российская федерация'}:status='excluded_source_country';reason='source_country_not_russia'
  if not finite_point(pos.get('latitude'),pos.get('longitude')):status='excluded_geometry';reason='invalid_provider_position'
  if active_date:
   if re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(active_date)):
    if str(active_date)<=snapshot:status='excluded_deactivated_on_or_before_snapshot';reason='explicit_source_deactivation_date'
   else:status='held_unparsed_deactivation';reason='deactivation_literal_not_interpreted'
  literal=', '.join(str(address.get(k)) for k in ['region','locality','street','house','housing','building'] if address.get(k))
  services=raw.get('pickup_services') or {}
  rows.append(dict(provider_id=prefix+':'+str(raw['id']),source_object_id=str(raw['id']),canonical_source_site_id=prefix+':'+str(raw['id']),
   source_operator_station_id=str(raw.get('operator_station_id','')),provider_operator_id=raw.get('operator_id'),
   operator='Yandex Market and partners' if is_yandex else '5Post',operator_code='yandex_market_partner' if is_yandex else '5post',source_name=raw.get('name'),
   source_record_id=None,service_code=service_code,alternative_to_service_code='parcel_pickup',
   counts_as_independent_service_channel=False,supply_status=status,eligibility_reason=reason,
   default_external_seed_eligible=status=='observed',site_lat=pos.get('latitude'),site_lon=pos.get('longitude'),
   source_id=source_prefix+'_PUBLIC_WIDGET_PICKUP_'+snapshot.replace('-',''),source_year=int(snapshot[:4]),source_snapshot=snapshot,
   source_year_basis='acquisition_date_source_observation_date_not_explicit',observation_year=None,
   source_url=YANDEX_WIDGET_URL,public_source_method='POST',source_country_literal=address.get('country'),
   activity_address=literal,source_address_locality=address.get('locality'),source_region_literal=address.get('region'),
   source_subregion_literal=address.get('subRegion'),provider_geo_id=address.get('geoId'),source_postal_code=address.get('postal_code'),
   deactivation_date_literal=active_date,deactivation_date_predicted_debt_literal=raw.get('deactivation_date_predicted_debt'),
   future_deactivation_announced=bool(active_date and str(active_date)>snapshot),
   source_is_yandex_branded=raw.get('is_yandex_branded'),source_is_market_partner=raw.get('is_market_partner'),
   source_is_post_office=raw.get('is_post_office'),source_is_dark_store=raw.get('is_dark_store'),
   source_available_for_dropoff=raw.get('available_for_dropoff'),source_available_for_c2c_dropoff=raw.get('available_for_c2c_dropoff'),
   pickup_services_json=json.dumps(services,ensure_ascii=False),payment_methods_json=json.dumps(raw.get('payment_methods'),ensure_ascii=False),
   opening_hours=json.dumps(raw.get('schedule'),ensure_ascii=False),
   evidence_kind='official_public_widget_structured_customer_pickup_record',location_precision='provider_published_coordinates',
   order_specific_eligibility_unknown=True,operator_compatibility_scope='Yandex_market_l4g_network_only_order_specific_rules_unknown' if is_yandex else '5Post_network_only_order_specific_rules_unknown',
   other_operator_can_replace_this_point_for_same_order=False,actual_operational_status_checked=False,observed_flow=False,capacity_known=False))
  if not is_yandex:rows[-1]['source_address_comment']=address.get('comment')
 d=pd.DataFrame(rows)
 if d.provider_id.duplicated().any():raise ValueError('Duplicate public Yandex point IDs')
 valid=d.site_lat.between(-90,90)&d.site_lon.between(-180,180)
 links=match_wb_addresses(d.loc[valid],reference,population_wide)
 # Preserve structured locality/region fields; only the resolved identity and
 # explicit proximity diagnostics are imported from the shared matcher.
 for col in links:d.loc[links.index,col]=links[col]
 d=bind_explicit_city_contexts(d,reference)
 return add_geographic_context(d,reference)

def build_yandex(source_path,reference_path,output,population_path=None,snapshot='2026-10-24',network_operator='market_l4g'):
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 payload=json.load(gzip.open(source_path,'rt',encoding='utf-8'))
 reference=pd.read_parquet(reference_path)
 population=pd.read_parquet(population_path,columns=['source_record_id_2021','settlement_type_2021']) if population_path else None
 suffix='yandex' if network_operator=='market_l4g' else '5post'
 sites=normalize_yandex(payload,reference,population,snapshot,network_operator);save(sites,out/('sites_'+suffix+'_current'))
 offers=np_offers(sites);offers['alternative_to_service_code']='parcel_pickup';offers['counts_as_independent_service_channel']=False
 save(offers,out/('supply_'+suffix+'_current'))
 accepted=sites[sites.supply_status.eq('observed')]
 if network_operator=='5post':write_grocery_host_variant(sites,out)
 summary={'source_points':len(sites),'eligible_customer_pickup_points':len(accepted),'strict_identity_offers':len(offers),
  'status_counts':sites.supply_status.value_counts().to_dict(),
  'source_operator_ids':sites.provider_operator_id.value_counts().to_dict(),'source_country_literals':sites.source_country_literal.value_counts().to_dict(),
  'explicit_source_region_literals':int(sites.source_region_literal.nunique()),'future_deactivation_announced':int(sites.future_deactivation_announced.sum()),
  'ordinary_identity_sites':int(accepted.source_population_role.eq('ordinary_settlement_record').sum()),
  'city_context_identity_sites':int(accepted.source_population_role.eq('external_context_nonadditive').sum()),
  'actual_flows_observed':False,'counts_as_independent_service_channel':False,
  'source_is_complete_network_inventory':False,'source_scope':'public_tariff_widget_'+network_operator+'_customer_pickup_points_not_warehouses_not_all_possible_contracts',
  'source_files':[{'path':str(p),'bytes':Path(p).stat().st_size,'sha256':digest(p)} for p in [source_path,reference_path]+([population_path] if population_path else [])]}
 coverage=pd.DataFrame({'region':sorted(reference.region.dropna().unique())})
 coverage['ordinary_np_denominator']=coverage.region.map(reference[reference.ordinary_spatial_2021].groupby('region').size()).fillna(0).astype(int)
 coverage['source_declared_point_count']=coverage.region.map(accepted.source_region_literal.map(normalize_region).value_counts()).fillna(0).astype(int)
 bound=accepted[accepted.source_record_id.notna()].merge(reference[reference.source_record_id.notna()][['source_record_id','region']],on='source_record_id',how='left',validate='many_to_one')
 coverage['strict_ordinary_np_with_source']=coverage.region.map(bound[bound.source_population_role.eq('ordinary_settlement_record')].groupby('region').source_record_id.nunique()).fillna(0).astype(int)
 coverage['explicit_nonadditive_city_contexts_with_source']=coverage.region.map(bound[bound.source_population_role.eq('external_context_nonadditive')].groupby('region').source_record_id.nunique()).fillna(0).astype(int)
 coverage['zero_does_not_prove_absent_network']=True
 save(coverage,out/('coverage_'+suffix+'_by_region'));coverage.to_csv(out/('coverage_'+suffix+'_by_region.csv'),index=False)
 (out/(suffix+'_summary.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))
 return summary

def save(frame,path):
 frame.to_parquet(path.with_suffix('.parquet'),index=False,compression='zstd')

def build(osm_path,wb_path,reference_path,legacy_path,output,population_path=None,snapshot='2026-10-24'):
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 reference=pd.read_parquet(reference_path);legacy=pd.read_parquet(legacy_path)
 osm=pd.read_parquet(osm_path);o=normalize_osm(osm,reference,legacy);save(o,out/'osm_source_ledger')
 payload=json.load(gzip.open(wb_path,'rt',encoding='utf-8'))
 population=pd.read_parquet(population_path,columns=['source_record_id_2021','settlement_type_2021']) if population_path else None
 w=normalize_wb(payload,reference,population,snapshot);save(w,out/'wb_all_points')
 allsites=bind_explicit_city_contexts(pd.concat([o,w],ignore_index=True,sort=False),reference)
 allsites=add_geographic_context(allsites,reference)
 # No cross-year object counts are combined. Source chronology remains queryable.
 save(allsites,out/'sites');supply=np_offers(allsites);save(supply,out/'supply')
 write_pickup_variants(allsites,out)
 eligible=allsites[allsites.supply_status.eq('observed')]
 regions=pd.DataFrame({'region':sorted(reference.region.dropna().unique())})
 ordinary_counts=reference[reference.ordinary_spatial_2021].groupby('region').size()
 context_counts=reference[reference.source_record_id.notna()&reference.population_role.eq('external_context_nonadditive')].groupby('region').size()
 regions['ordinary_np_denominator']=regions.region.map(ordinary_counts).fillna(0).astype(int)
 regions['nonadditive_city_context_denominator']=regions.region.map(context_counts).fillna(0).astype(int)
 coverage=[]
 for (code,snapshot),group in eligible.groupby(['service_code','source_snapshot']):
  strict=group[group.source_record_id.notna()].merge(reference[reference.source_record_id.notna()][['source_record_id','region']],on='source_record_id',how='left',validate='many_to_one')
  p=strict[~strict.source_population_role.eq('external_context_nonadditive')].groupby('region').source_record_id.nunique()
  city=strict[strict.source_population_role.eq('external_context_nonadditive')].groupby('region').source_record_id.nunique()
  geom=group.groupby('regional_context_proxy').provider_id.nunique()
  rows=regions.copy();rows['service_code']=code;rows['source_snapshot']=snapshot
  rows['np_with_strict_source_identity']=rows.region.map(p).fillna(0).astype(int)
  rows['nonadditive_city_contexts_with_explicit_source_identity']=rows.region.map(city).fillna(0).astype(int)
  rows['sites_in_nearest_np_region_proxy']=rows.region.map(geom).fillna(0).astype(int)
  rows['zero_means_no_source_witness_not_no_service']=True;coverage.append(rows)
 cov=pd.concat(coverage,ignore_index=True);save(cov,out/'coverage_by_region');cov.to_csv(out/'coverage_by_region.csv',index=False)
 summary={'raw_osm_rows':len(osm),'raw_wb_publisher_ru_rows':len(w),'normalized_sites_all_statuses':len(allsites),
  'eligible_mapped_service_sites':len(eligible),'strict_np_service_source_offers':len(supply),
  'national_regions_in_reference':len(regions),'source_presence_is_complete_inventory':False,
  'actual_flows_observed':False,'counts_used_as_attraction_weights':False,
  'eligible_by_source_service':eligible.groupby(['source_id','service_code']).size().rename('sites').reset_index().to_dict('records'),
  'status_counts':allsites.supply_status.value_counts().to_dict(),
  'strict_identity_site_count':int(eligible.source_record_id.notna().sum()),
  'ordinary_np_identity_site_count':int(eligible.source_population_role.eq('ordinary_settlement_record').sum()),
  'nonadditive_city_context_identity_site_count':int(eligible.source_population_role.eq('external_context_nonadditive').sum()),
  'strict_ordinary_np_coverage_by_service':eligible[eligible.source_population_role.eq('ordinary_settlement_record')].groupby('service_code').source_record_id.nunique().to_dict(),
  'explicit_city_context_coverage_by_service':eligible[eligible.source_population_role.eq('external_context_nonadditive')].groupby('service_code').source_record_id.nunique().to_dict(),
  'rarity_or_order_of_other_retail_observed':False,'date_difference_means_openings_or_closures':False,
  'strict_np_coverage_by_service':eligible.groupby('service_code').source_record_id.nunique().to_dict(),
  'region_proxy_coverage_by_service':eligible.groupby('service_code').regional_context_proxy.nunique().to_dict(),
  'source_files':[{ 'path':str(p),'bytes':Path(p).stat().st_size,'sha256':digest(p)} for p in [osm_path,wb_path,reference_path,legacy_path]+([population_path] if population_path else [])]}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,ensure_ascii=False))
 return summary

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='fetch-yandex':
  p=argparse.ArgumentParser(description='Read the official anonymous Yandex public widget endpoint')
  p.add_argument('--output',type=Path,required=True);p.add_argument('--snapshot',default='2026-10-24');p.add_argument('--expected-sha256');p.add_argument('--operator',choices=['market_l4g','5post'],default='market_l4g')
  a=p.parse_args(sys.argv[2:]);print(acquire_yandex_public_widget(a.output,a.snapshot,a.expected_sha256,a.operator)[1]);raise SystemExit(0)
 if len(sys.argv)>1 and sys.argv[1] in {'yandex','fivepost'}:
  p=argparse.ArgumentParser(description='Normalize a frozen official public Yandex pickup source')
  p.add_argument('--source',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--population',type=Path)
  p.add_argument('--output',type=Path,required=True);p.add_argument('--snapshot',default='2026-10-24')
  a=p.parse_args(sys.argv[2:]);build_yandex(a.source,a.reference,a.output,a.population,a.snapshot,'market_l4g' if sys.argv[1]=='yandex' else '5post');raise SystemExit(0)
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--osm',type=Path,required=True);p.add_argument('--wb',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--legacy',type=Path,required=True);p.add_argument('--population',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--wb-snapshot',default='2026-10-24');a=p.parse_args()
 build(a.osm,a.wb,a.reference,a.legacy,a.output,a.population,a.wb_snapshot)
