import json,csv,re,html,math,hashlib,collections
from pathlib import Path
import pyarrow as pa,pyarrow.parquet as pq
E=Path(__file__).resolve().parent;P=E.parent
old={x['source_record_id']for f in ['rsfsr1989_external_points_20261013/external_point_delta.csv','rsfsr1989_external_points_delta2_20261013/external_point_delta2.csv','rsfsr1989_external_points_delta3_20261013/external_point_delta3.csv']for x in csv.DictReader(open(P/f))};raw=[x for x in csv.DictReader(open(P/'rsfsr1989_primary_binding_20261013/primary_bindings.csv'))if not x['binding_status'].startswith('bound')and x['source_record_id']not in old];selected=json.load(open(E/'selected_candidates.json'));receipts={x['qid']:x for x in json.load(open(E/'entity_receipts.json'))};corepath=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
def norm(s):return' '.join(re.sub('[^а-я0-9]+',' ',s.lower().replace('ё','е')).split())
def vals(d,k):return[(z['mainsnak'].get('datavalue',{}).get('value'),z.get('rank'))for z in d.get('claims',{}).get(k,[])if z.get('rank')!='deprecated']
def dist(a,b):
 v=list(map(math.radians,[a['latitude'],a['longitude'],b['latitude'],b['longitude']]));return 6371*2*math.asin(min(1,math.sqrt(math.sin((v[2]-v[0])/2)**2+math.cos(v[0])*math.cos(v[2])*math.sin((v[3]-v[1])/2)**2)))
# Keep a small qualified-name slice of the existing core; no graph edits.
labels={}
corehash=hashlib.sha256(corepath.read_bytes()).hexdigest()
for name,q in selected.items():
 d=json.load(open(E/('entity_'+q+'.json')))['entities'][q];labels[name]=re.sub(r'\s*\([^)]*\)$','',d.get('labels',{}).get('ru',{}).get('value',''))
current=collections.defaultdict(list)
labelnorms={norm(n)for n in labels.values()}
for b in pq.ParquetFile(corepath).iter_batches(columns=['source_record_id','root','census_year','settlement_name','settlement_type','region_norm','district_raw','population_scope','is_additive_settlement_record','accepted_point_present','accepted_latitude','accepted_longitude'],batch_size=8192):
 for z in b.to_pylist():
  if norm(z['settlement_name']or'')not in labelnorms:continue
  if z['population_scope']in['region','federal_city_region','federal_territory','municipality','district','aggregate']or z['is_additive_settlement_record']is False:continue
  current[(z['region_norm'],norm(z['settlement_name']or''))].append(z)
out=[];checks=[]
for x in raw:
 name=x['source_name_parsed_for_binding'];q=selected.get(name)
 if not q:continue
 rr=receipts[q];fp=E/rr['path'];d=json.load(open(fp))['entities'][q];label=labels[name];
 if name=='Мамонтово'and x['current_region_alias']!='алтайский':continue
 if name=='Красный Октябрь'and x.get('administrative_heading_raw')!='Киржачский район':continue
 aliases=[z['value']for z in d.get('aliases',{}).get('ru',[])];desc=d.get('descriptions',{}).get('ru',{}).get('value','');cl=[z.get('id')for z,rk in vals(d,'P31')if isinstance(z,dict)];art=rr.get('article');text=' '.join(html.unescape(re.sub('<[^>]+>',' ',(E/art['path']).read_text())).split())if art else''
 same=norm(name)==norm(label);explicit=norm(name)in norm(text)or norm(name)in{norm(z)for z in aliases};orthographic=name=='Кинель-Черкасы'and label=='Кинель-Черкассы';former='упразднённый рабочий поселок'in text or 'упразднённый рабочий посёлок'in text
 district_center_source='(рц)'in x.get('settlement_label_raw',x.get('label_raw',''))
 district_center_publication=('центр' in text and ('района'in text or 'муниципального'in text))
 source_county=x.get('administrative_heading_raw','')
 physical=bool(set(cl)&{'Q515','Q7930989','Q532','Q5084','Q2514025','Q15078955','Q486972','Q748331'})or former
 pcs=[(z,rk)for z,rk in vals(d,'P625')if isinstance(z,dict)and z.get('globe','').endswith('/Q2')and all(math.isfinite(z[k])for k in ['latitude','longitude'])];maxkm=max([dist(a,b)for a,ar in pcs for b,br in pcs],default=0);consistent=bool(pcs)and maxkm<=5;preferred=[(z,rk)for z,rk in pcs if rk=='preferred'];chosen=(preferred[0]if len(preferred)==1 else min(pcs,key=lambda a:a[0].get('precision',1)or 1))if consistent else None
 regions=x['current_region_alias'].split('|');cands=[z for r in regions for z in current.get((r,norm(label)),[])];cands=[z for z in cands if z['accepted_point_present']and z['accepted_latitude']is not None and z['accepted_longitude']is not None and all(math.isfinite(z[k])for k in ['accepted_latitude','accepted_longitude'])];near=[z for z in cands if chosen and dist(chosen[0],dict(latitude=z['accepted_latitude'],longitude=z['accepted_longitude']))<=5];rootchoice=None
 for cy in [2021,2010,2002]:
  cyrows=[z for z in near if z['census_year']==cy]
  if cyrows:
   if len({z['root']for z in cyrows})==1:rootchoice=cyrows[0]
   break
 regiondoc=bool(near)or any(t in norm(desc+' '+text)for r in regions for t in [{'липецкая':'липецк','краснодарский':'краснодар','красноярский':'красноярск','самарская':'самарск','оренбургская':'оренбургск','коми':'коми','башкортостан':'башкортостан','пензенская':'пензенск','тамбовская':'тамбовск','камчатский':'камчатск','приморский':'приморск','ростовская':'ростовск','алтайский':'алтайск','нижегородская':'нижегородск','санкт петербург':'санкт петербург'}.get(r,r)])
 ok=(same or explicit or orthographic)and physical and consistent and regiondoc
 if district_center_source and not district_center_publication:ok=False
 j=text.lower().find(name.lower(),10000);quote=text[max(0,j-130):j+400]if j>=0 else ('Published current name: '+label+'; old single-с spelling is explicit user-authorized printed variant, not a documented legal rename'if orthographic else'')
 note=dict(source_record_id=x['source_record_id'],name=name,qid=q,current_name=label,P31=cl,name_literal=same,explicit_publication_name=explicit,authorized_orthographic_variant=orthographic,former_np_publication=former,source_district_center_role=district_center_source,current_district_center_publication=district_center_publication,source_county_heading=source_county,physical_grain_proof=physical,region_proof=regiondoc,finite_points=len(pcs),max_provider_distance_km=maxkm,selected_precision=chosen[0].get('precision')if chosen else None,status='accepted'if ok else'held',history_quote=quote);checks.append(note)
 if not ok:continue
 c=chosen[0];z=dict(x);grade='multiple_consistent_provider_points'if len(pcs)>1 else'current_neighbourhood_point_of_explicitly_documented_former_settlement'if former else'qualified_external_physical_place_current_point_historical_continuity_inferred';root='historical:1989:demoscope:'+q;anchor=None;year=None;lat=c['latitude'];lon=c['longitude'];status='bound_external_physical_point_historical_entity'
 if rootchoice:
  root=rootchoice['root'];anchor=rootchoice['source_record_id'];year=rootchoice['census_year'];lat=rootchoice['accepted_latitude'];lon=rootchoice['accepted_longitude'];status='bound_explicit_published_variant_unique_current_np_accepted_ownpoint';grade='existing_accepted_ownpoint_explicit_historical_variant_reference'
 z.update(root=root,anchor_source_record_id=anchor,anchor_census_year=year,binding_status=status,coordinate_role=grade,accepted_latitude=lat,accepted_longitude=lon,external_id=q,current_name=label,current_region=x['current_region_alias'],individual_2021_census_status='existing_individual_reference_'+str(year)if anchor else'no_individual_2021_census_bound',binding_rule='literal_or_published_variant_or_explicit_authorized_printed_variant+qualified_region+physical_place+consistent_P625',coordinate_source_url=rr['url'],coordinate_source_sha256=rr['sha256'],coordinate_source_locator='entities.'+q+'.claims.P625',point_identity_grade=grade,population_basis='present',historical_boundary_comparability='unknown',retrospective_current_point_inference=True,history_source_url=art['url']if art else'',history_source_sha256=art['sha256']if art else'',history_quote=quote,provider_coordinate_count=len(pcs),provider_max_distance_km=maxkm,selected_provider_precision=c.get('precision'));out.append(z)
official=json.load(open(E/'tatsinsky_official_identity_receipt.json'))
for z in out:
 if z['source_name_parsed_for_binding']=='Тацинский':
  z['history_official_source_url']=official['source_url'];z['history_official_source_sha256']=official['source_pdf_sha256'];z['history_official_locator']=official['footnote_locator'];z['history_official_quote']=official['literal_quote']
 z['external_entity_validation_url']=z['coordinate_source_url'];z['external_entity_validation_sha256']=z['coordinate_source_sha256']
 if z['binding_status']=='bound_explicit_published_variant_unique_current_np_accepted_ownpoint':
  z['coordinate_source_url']=str(corepath);z['coordinate_source_sha256']=corehash;z['coordinate_source_locator']='source_record_id='+z['anchor_source_record_id']+';accepted_latitude;accepted_longitude'
fields=list(dict.fromkeys(k for x in out for k in x))
with(E/'external_point_delta4.csv').open('w')as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
pq.write_table(pa.Table.from_pylist([{k:z.get(k)for k in fields}for z in out]),E/'external_point_delta4.parquet',compression='zstd');(E/'entity_validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2));r=dict(rows=len(out),population_total=sum(int(x['population_total'])for x in out),population_basis='present',source='Demoscope only',core_sha256=corehash,root_duplicates=len(out)-len({x['root']for x in out}),source_uid_duplicates=len(out)-len({x['source_record_id']for x in out}),prior_delta_overlap=sum(x['source_record_id']in old for x in out),finite_coordinate_failures=sum(not all(math.isfinite(x[k])for k in ['accepted_latitude','accepted_longitude'])for x in out),grade_profiles=[dict(grade=k,rows=sum(x['point_identity_grade']==k for x in out),population_total=sum(int(x['population_total'])for x in out if x['point_identity_grade']==k))for k in sorted({x['point_identity_grade']for x in out})],outputs={n:hashlib.sha256((E/n).read_bytes()).hexdigest()for n in ['external_point_delta4.csv','external_point_delta4.parquet']},held=[x for x in checks if x['status']=='held']);(E/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
