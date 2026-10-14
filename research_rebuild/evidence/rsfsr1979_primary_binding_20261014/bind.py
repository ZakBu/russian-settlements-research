#!/usr/bin/env python3
import csv,json,re,math,hashlib,collections
from pathlib import Path
import pyarrow as pa,pyarrow.parquet as pq
E=Path(__file__).resolve().parent; BASE=E.parent
CORE=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
def norm(x):return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',(x or '').lower().replace('ё','е')).split())
alias={'Ставропольский край':['ставропольский','карачаево черкесская'],'Краснодарский край':['краснодарский','адыгея'],'Алтайский край':['алтайский','алтай'],'г. Ленинград':'санкт петербург','г. Москва':'москва','Башкирская АССР':'башкортостан','Бурятская АССР':'бурятия','Кабардино-Балкарская АССР':'кабардино балкарская','Калмыцкая АССР':'калмыкия','Карельская АССР':'карелия','Коми АССР':'коми','Марийская АССР':'марий эл','Мордовская АССР':'мордовия','Северо-Осетинская АССР':'северная осетия алания','Татарская АССР':'татарстан','Тувинская АССР':'тыва','Удмуртская АССР':'удмуртская','Чувашская АССР':'чувашская','Якутская АССР':'саха якутия','Дагестанская АССР':'дагестан','Адыгейская автономная область':'адыгея','Горно-Алтайская автономная область':'алтай','Хакасская автономная область':'хакасия','Карачаево-Черкесская автономная область':'карачаево черкесская','Горьковская область (ныне Нижегородская)':'нижегородская','Калининская область (ныне Тверская)':'тверская','Куйбышевская область (ныне Самарская)':'самарская','Пермская область':'пермский','Камчатская область':'камчатский','Читинская область':'забайкальский','Ханты-Мансийский автономный округ':'ханты мансийский югра','Ямало-Ненецкий автономный округ':'ямало ненецкий','Ненецкий автономный округ':'ненецкий','Чукотский автономный округ':'чукотский','Еврейская автономная область':'еврейская','Агинский Бурятский автономный округ':'забайкальский','Усть-Ордынский Бурятский автономный округ':'иркутская','Коми-Пермяцкий автономный округ':'пермский','Корякский автономный округ':'камчатский','Таймырский (Долгано-Ненецкий) автономный округ':'красноярский','Эвенкийский автономный округ':'красноярский','Чечено-Ингушская АССР':['чеченская','ингушетия'],'г. Москва и населенные пункты, подчиненные Московскому горсовету':'москва'}
# Current region aliases are namespace qualification, not asserted 1989 boundary equivalence.
def reg(s):
 if s.startswith('г. Москва'):return ['москва']
 if s in alias:return alias[s]if isinstance(alias[s],list)else[alias[s]]
 return[norm(re.sub(r'\s+(область|край)$','',s))]
index=collections.defaultdict(list);byroot=collections.defaultdict(list)
cols=['source_record_id','census_year','settlement_name','settlement_type','name_norm','region_norm','district_raw','population_scope','is_additive_settlement_record','root','accepted_point_present','accepted_latitude','accepted_longitude']
for batch in pq.ParquetFile(CORE).iter_batches(batch_size=8192,columns=cols):
 for r in batch.to_pylist():
  byroot[r['root']].append(r)
  if r['population_scope'] in ['district','region','federal_territory','municipality','aggregate'] or r['is_additive_settlement_record']is False:continue
  index[(r['region_norm'],norm(r['settlement_name']))].append(r)
FEDERAL=Path('/workspace/scratch/tochno-enrichment-20261013/package/links/accepted_common_federal_territory_axis.csv')
federal={x['region_norm']:x for x in csv.DictReader(open(FEDERAL))if x['census_year']=='2021'}
def km(a,b):
 lat1,lon1,lat2,lon2=map(math.radians,[a['accepted_latitude'],a['accepted_longitude'],b['accepted_latitude'],b['accepted_longitude']]);return 6371*2*math.asin(min(1,math.sqrt(math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2)))
seed={}
for x in csv.DictReader(open(BASE/'rsfsr1989_urban_mass_20261013/image_checked_source_current_reference_bindings.csv')):
 seed[(x['current_region_qualified_rule'],norm(x['printed_name_image_verified']))]=(x['current_reference_root'],x['current_reference_name_rule'],x['name_alias_rule'])
sources=[]
for sub,fn in [('rsfsr1979_urban_mass_20261014','urban_settlements_1979.csv'),('rsfsr1979_urban_mass_20261014','rural_centres_1979.csv')]:
 rows=list(csv.DictReader(open(BASE/sub/fn)));lastreg=''
 headers=json.load(open(BASE/sub/('rural_source_headers.json' if fn.startswith('rural') else 'source_headers.json'))); qualified_by_tr={}; active=''
 for h in headers:
  v=h.get('label_raw',h.get('label'));
  if v in ['Ленинградский горсовет','г. Ленинград']:active='Санкт-Петербург'
  elif v.startswith('г. Москва'):active=v
  elif (v in alias or re.search(r' (область|край|АССР|автономный округ)$',v)) and 'горсовет'not in v:active=v
  qualified_by_tr[h['html_tr']]=active
 import bisect
 hkeys=sorted(qualified_by_tr)
 for x in rows:
  tr=int(re.search(r'html_tr:(\d+)',x['source_record_id']).group(1));hk=bisect.bisect_left(hkeys,tr)-1
  region=x['region_label_raw'];heading=x.get('administrative_heading_raw','');label=x.get('label_raw',x.get('settlement_label_raw',''))
  if not region and 'Ленинградский горсовет'in heading:region='Санкт-Петербург'
  if any(z in region for z in ['горсовет','рп Гоуджекит']) and not region.startswith('г. Москва'):region=lastreg
  else:lastreg=region
  if region=='Санкт-Петербург':alias[region]='санкт петербург'
  name=x.get('source_parsed_name')or re.sub(r'^(с\.|п\.|ст\.|ст-ца|сл\.|д\.|аул|станица|село|пос)\s*','',label)
  name=name.split('(',1)[0].strip();regions=reg(region);candidates=[]
  historic_city_aliases={('нижегородская','горький'):'Нижний Новгород',('самарская','куйбышев'):'Самара',('тверская','калинин'):'Тверь',('северная осетия алания','орджоникидзе'):'Владикавказ',('марий эл','иошкар ола'):'Йошкар-Ола',('воронежская','георгиу деж'):'Лиски'}
  current_alias=next((historic_city_aliases[(rg,norm(name))]for rg in regions if (rg,norm(name))in historic_city_aliases),None)
  for rg in regions:candidates+=index.get((rg,norm(name)),[])
  rule='literal_name_region_unique_root'
  if not candidates and current_alias:
   for rg in regions:candidates+=index.get((rg,norm(current_alias)),[])
   rule='explicit_parent_authorized_historic_city_alias:'+name+'→'+current_alias
  roots={r['root']for r in candidates}
  if not roots:
   for rg in regions:
    z=seed.get((rg,norm(name)))
    if z:candidates+=byroot.get(z[0],[]);rule='existing_image_checked_explicit_city_alias:'+z[2]
   roots={r['root']for r in candidates}
  if len(roots)>1:
   sd=norm(heading or '');qualified=[r for r in candidates if sd and norm(r['district_raw'])==sd]
   qr={r['root']for r in qualified}
   if len(qr)==1:candidates=qualified;roots=qr;rule='literal_name_region_exact_source_district_unique_root'
  all_type_candidate_roots='|'.join(sorted(roots))
  source_type=x.get('settlement_type_raw','')
  compatible_types={'город'}if source_type=='г.'else {'город','пгт'}if source_type in ['рп','кп','дп','пгт']else None
  if len(roots)>1 and compatible_types:
   typed=[z for z in candidates if z['settlement_type']in compatible_types]
   if typed:candidates=typed;roots={z['root']for z in typed};rule='literal_name_region_source_type_qualified_physical_np'
  older_far=False
  if len(roots)>1:
   for cy in [2021,2010,2002]:
    snapshot=[r for r in candidates if r['census_year']==cy];sr={r['root']for r in snapshot}
    if not snapshot:continue
    if len(sr)==1:
     sp=[r for r in snapshot if r['accepted_point_present']and r['accepted_latitude']is not None and r['accepted_longitude']is not None]
     older=[r for r in candidates if r['root']not in sr and r['accepted_point_present']and r['accepted_latitude']is not None and r['accepted_longitude']is not None]
     older_far=bool(sp)and any(km(sp[0],z)>5 for z in older)
     if not older_far:candidates=snapshot;roots=sr;rule='unique_latest_physical_snapshot_'+str(cy)+'_older_finite_rivals_within_5km_or_unresolved_without_point'
    break
  pointrows=[r for r in candidates if r['accepted_point_present'] and all(isinstance(r[k],(float,int))and math.isfinite(r[k])for k in ['accepted_latitude','accepted_longitude'])]
  pointset={(r['accepted_latitude'],r['accepted_longitude'])for r in pointrows}
  status='bound_unique_root_accepted_ownpoint'if len(roots)==1 and bool(pointrows) else ('competing_roots'if len(roots)>1 else 'missing_name_region_candidate'if not roots else 'missing_or_conflicting_accepted_point')
  coordinate_role='accepted_settlement_ownpoint_reused_as_historical_reference'
  if norm(name)in ['ленинград','москва']and regions[0]in federal:
   f=federal[regions[0]];cr=byroot.get(f['coordinate_source_record_id'],[])
   if cr:
    chosen_f=dict(cr[0]);chosen_f['accepted_latitude']=float(f['latitude']);chosen_f['accepted_longitude']=float(f['longitude']);pointrows=[chosen_f];roots={chosen_f['root']};status='bound_existing_territorial_reference_as_historical_city_center_inferred_continuity';coordinate_role='accepted_territorial_reference_point_used_for_historical_city_center_inferred_continuity';rule='explicit_user_authorized_existing_common_federal_representative_axis_cityproper_only'
  chosen=sorted(pointrows,key=lambda r:-r['census_year'])[0]if status.startswith('bound')else None
  out=dict(x);out.update(binding_status=status,binding_rule=rule,all_type_candidate_roots=all_type_candidate_roots,coordinate_role=coordinate_role,genuine_far_older_rival_detected=older_far,qualified_historical_region=region,current_region_alias='|'.join(regions),source_name_parsed_for_binding=name,candidate_root_count=len(roots),candidate_roots='|'.join(sorted(roots)),root=chosen['root']if chosen else '',anchor_source_record_id=chosen['source_record_id']if chosen else '',anchor_census_year=chosen['census_year']if chosen else None,current_name=chosen['settlement_name']if chosen else '',current_type=chosen['settlement_type']if chosen else '',accepted_latitude=chosen['accepted_latitude']if chosen else None,accepted_longitude=chosen['accepted_longitude']if chosen else None,current_source_years='|'.join(map(str,sorted({r['census_year']for r in candidates}))),historical_boundary_comparability='unknown',retrospective_current_point_inference=True,scope_note='city_proper_not_full_federal_territory'if norm(name)in ['москва','ленинград']else 'source_named_settlement')
  sources.append(out)
fields=list(dict.fromkeys(k for x in sources for k in x));
with(E/'primary_bindings.csv').open('w')as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(sources)
# Uniform string source attributes with numeric binding coordinates preserved.
rows=[{k:x.get(k)for k in fields}for x in sources];pq.write_table(pa.Table.from_pylist(rows),E/'primary_bindings.parquet',compression='zstd')
bound=[x for x in sources if x['binding_status'].startswith('bound')];unbound=sorted([x for x in sources if not x['binding_status'].startswith('bound')],key=lambda x:-int(x['population_total']))
r=dict(source_rows=len(sources),source_population=sum(int(x['population_total'])for x in sources),bound_rows=len(bound),bound_population=sum(int(x['population_total'])for x in bound),unique_bound_roots=len({x['root']for x in bound}),ordinary_ownpoint_rows=sum(x['binding_status']=='bound_unique_root_accepted_ownpoint'for x in bound),ordinary_ownpoint_population=sum(int(x['population_total'])for x in bound if x['binding_status']=='bound_unique_root_accepted_ownpoint'),authorized_federal_reference_rows=sum(x['binding_status'].startswith('bound_existing_territorial')for x in bound),authorized_federal_reference_population=sum(int(x['population_total'])for x in bound if x['binding_status'].startswith('bound_existing_territorial')),federal_axis_sha256=hashlib.sha256(FEDERAL.read_bytes()).hexdigest(),status_counts=dict(collections.Counter(x['binding_status']for x in sources)),largest_unbound=[dict(name=x['source_name_parsed_for_binding'],region=x['qualified_historical_region'],population=int(x['population_total']),status=x['binding_status'])for x in unbound[:30]],core_sha256=hashlib.sha256(CORE.read_bytes()).hexdigest(),outputs={n:hashlib.sha256((E/n).read_bytes()).hexdigest()for n in ['primary_bindings.csv','primary_bindings.parquet']})
r['bound_root_duplicate_groups']=[dict(root=k,source_record_ids=[z['source_record_id']for z in bound if z['root']==k])for k,n in collections.Counter(z['root']for z in bound).items()if n>1]
r['source_uid_duplicates']=len(sources)-len({z['source_record_id']for z in sources})
r['finite_bound_coordinate_failures']=sum(not all(isinstance(z[k],(int,float))and math.isfinite(z[k])for k in ['accepted_latitude','accepted_longitude'])for z in bound)
(E/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));(E/'region_aliases.json').write_text(json.dumps(alias,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
