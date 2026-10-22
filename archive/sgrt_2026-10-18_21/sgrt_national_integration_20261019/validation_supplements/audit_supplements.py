#!/usr/bin/env python3
"""Small, separate PickPoint and federal-row audit; never reads all914 fields.

Parquet selections use at most three columns per call. Exact-name candidates
are reconstructed by a relational join, not the author's grouped-row lookup.
"""
from pathlib import Path
import re,json,hashlib,unicodedata
import numpy as np,pandas as pd,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;N=H.parent;B=N.parent
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(2**20),b''):h.update(x)
 return h.hexdigest()
def text(v):return ' '.join(re.findall(r'[а-яa-z0-9]+',str(v).lower().replace('ё','е'))) if pd.notna(v) else ''
def region(v):
 s=' '.join(x for x in text(v).split() if x not in {'респ','республика','обл','область','край','авт','автономный','автономная','округ'});return {'ингушская':'ингушетия','чечня':'чеченская','чувашия':'чувашская'}.get(s,s)
RULES=[('urban_settlement',r'пгт|п\.?\s*г\.?\s*т\.?|рп|рабочий поселок'),('city',r'город|г\.'),('village',r'деревня|д\.'),('selo',r'село|с\.'),('stanitsa',r'станица|ст-ца|стца'),('settlement_unspecified',r'поселок|пос\.|п\.')]
FAMILIES={'city':{'город'},'village':{'деревня'},'selo':{'село'},'stanitsa':{'станица'},'urban_settlement':{'пгт'},'settlement_unspecified':{'посёлок','поселок','пгт','населённый пункт','населенный пункт'}}
def explicit_type(address,name):
 # Search all pre/suffix expressions, then prioritize segment and grammar order.
 hits=[]
 for si,segment in enumerate(str(address).lower().replace('ё','е').split(',')):
  for priority,(kind,grammar) in enumerate(RULES):
   for pattern in [r'^\s*(?:'+grammar+r')\s+(.+?)\s*$',r'^\s*(.+?)\s+(?:'+grammar+r')\s*$']:
    m=re.match(pattern,segment)
    if m and text(m.group(1))==text(name):hits.append((si,priority,kind))
 return min(hits)[2] if hits else 'not_explicit'
def same(a,b):
 if pd.isna(a) and pd.isna(b):return True
 if isinstance(a,(float,int,np.number,bool)) and isinstance(b,(float,int,np.number,bool)):return bool(np.isclose(a,b,rtol=1e-12,atol=1e-10,equal_nan=True))
 return str(a)==str(b)
def main():
 H.mkdir(parents=True,exist_ok=True);checks=[];inputs={};maxcols=0
 def ck(k,v,detail=None):checks.append({'name':k,'pass':bool(v),'detail':detail})
 def track(p):inputs[str(p)]=sha(p)
 def read(p,columns=None,filters=None):
  nonlocal maxcols
  p=Path(p)
  if str(p) not in inputs:track(p)
  if p.suffix!='.parquet':return pd.read_csv(p)
  assert columns is not None and len(columns)<=3,'No wide reads in this supplement';maxcols=max(maxcols,len(columns));return pd.read_parquet(p,columns=columns,filters=filters)
 ap=B/'anchor_research_20261019/data/point_axis.parquet';axis=read(ap,['id','name','region']).merge(read(ap,['id','type']),on='id',validate='one_to_one');axis['name_key']=axis.name.map(text);axis['region_key']=axis.region.map(region)
 sp=B/'functional_dynamics_20261019/marketplaces/pickpoint_extracted_202102.csv';source=read(sp);cp=N/'services_pickpoint/pickpoint_objects_crosswalk.parquet';cc=pq.ParquetFile(cp).schema_arrow.names;parts=[]
 for i in range(0,len(cc)-1,2):
  cols=[c for c in cc if c!='object_id'][i:i+2]
  if cols:parts.append(read(cp,['object_id']+cols).set_index('object_id'))
 cross=pd.concat(parts,axis=1).reset_index();ck('unfiltered_crosswalk_exact_source_keyset',len(cross)==3005 and cross.object_id.is_unique and set(cross.object_id)==set(source.object_id));cross=cross.set_index('object_id').reindex(source.object_id).reset_index();ck('all3005_sourceIDs_once',len(source)==len(cross)==3005 and source.object_id.is_unique and cross.object_id.is_unique)
 for c in source:ck('source_field_'+c,all(same(a,b) for a,b in zip(source[c],cross[c])))
 source['name_key']=source.settlement_name.map(text);source['region_key']=source.source_region.map(region);source['explicit_type_independent']=[explicit_type(a,n) for a,n in zip(source.address,source.settlement_name)]
 fedmap={'москва':'RU-FED-MOW','санкт петербург':'RU-FED-SPB'};fed=source.name_key.map(fedmap);ordinary=source[fed.isna()].merge(axis[['id','name_key','region_key','type']],on=['name_key','region_key'],how='left',validate='many_to_many');valid_type=ordinary.explicit_type_independent.eq('not_explicit')|pd.Series([t in FAMILIES.get(k,set()) for t,k in zip(ordinary.type,ordinary.explicit_type_independent)],index=ordinary.index);matches=ordinary[ordinary.id.notna()&valid_type];lists=matches.groupby('object_id').id.agg(list);counts=source.object_id.map(lists.map(len)).fillna(0).astype(int);uid=source.object_id.map(lists.map(lambda a:a[0] if len(a)==1 else None)).where(fed.isna());ck('all_exact_name_region_type_candidates',all(set((b or '').split('|'))- {''}==set(a or []) for a,b in zip(source.object_id.map(lists).map(lambda x:x if isinstance(x,list) else []),cross.candidate_uids.fillna(''))));ck('all_ordinary_UID_decisions',uid.fillna('').eq(cross.settlement_uid.fillna('')).all());ck('all_explicit_types',source.explicit_type_independent.eq(cross.source_explicit_type).all());ck('all_federal_UID_decisions',fed.fillna('').eq(cross.federal_territory_uid.fillna('')).all())
 ordinary_count=int(uid.notna().sum());fedcount=int(fed.notna().sum());ambiguous=int((fed.isna()&counts.gt(1)).sum());unresolved=int((fed.isna()&counts.eq(0)).sum());ck('source_partition_2282_505_121_97',(ordinary_count,fedcount,ambiguous,unresolved)==(2282,505,121,97));ck('ordinary_UID480',uid.nunique()==480)
 # Region label in this source is coarse oblast; require an explicit city
 # segment in the actual address for every federal record, not region alone.
 federal_review=[]
 for i in np.flatnonzero(fed.notna()):
  r=source.iloc[i];target='москва' if fed.iloc[i]=='RU-FED-MOW' else 'санкт петербург';segments=[re.sub(r'^(?:город|г)\s+','',text(x)) for x in str(r.address).split(',')[:3]];city=target in segments;macro=region(r.source_region)==('московская' if target=='москва' else 'ленинградская');federal_review.append({'object_id':r.object_id,'federal_uid':fed.iloc[i],'source_region':r.source_region,'address':r.address,'explicit_city_segment':city,'coarse_oblast_context_consistent':macro})
 fr=pd.DataFrame(federal_review);fr.to_csv(H/'pickpoint_all505_federal_address_audit.csv',index=False);ck('all505_actual_addresses_explicit_city',fr.explicit_city_segment.all());ck('all505_coarse_oblast_context_consistent',fr.coarse_oblast_context_consistent.all())
 keys=source.address.map(lambda a:unicodedata.normalize('NFKC',str(a)).strip().lower().replace('ё','е'));ops=source.operator_label.map(lambda x:re.sub(r'^ПВЗ:\s*','',str(x)).split(':')[0].strip());tab=pd.DataFrame({'uid':uid,'federal':fed,'address_key':keys,'operator':ops});fp=N/'services_pickpoint/pickpoint_settlement_features.parquet';features=read(fp,['id','pickpoint2021_source_schedule_rows','pickpoint2021_distinct_exact_address_keys']).set_index('id').reindex(axis.id);features['pickpoint2021_distinct_operator_labels']=read(fp,['id','pickpoint2021_distinct_operator_labels']).set_index('id').reindex(axis.id).iloc[:,0];ck('all142570_once',len(features)==142570 and features.index.is_unique)
 feature_keys=read(fp,['id']);ck('unfiltered_feature_exact_axis_keyset',len(feature_keys)==142570 and feature_keys.id.is_unique and set(feature_keys.id)==set(axis.id))
 for c,stat in [('pickpoint2021_source_schedule_rows',tab.groupby('uid').size()),('pickpoint2021_distinct_exact_address_keys',tab.groupby('uid').address_key.nunique()),('pickpoint2021_distinct_operator_labels',tab.groupby('uid').operator.nunique())]:ck('all_UID_'+c,np.array_equal(stat.reindex(axis.id,fill_value=0),features[c]))
 for c,value in [('pickpoint2021_snapshot_date','2021-02-20'),('pickpoint2021_zero_means','no_accepted_dated_source_witness_not_function_absence'),('pickpoint2021_evidence_scope','one_partner_network_schedule_not_complete_all_operator_network'),('pickpoint2021_comparable_time_series_with_WB2026',False),('pickpoint2021_external_catchment_measured',False)]:ck('all_UID_metadata_'+c,read(fp,['id',c])[c].eq(value).all())
 pp=N/'services_pickpoint/pickpoint_federal_features.parquet';ff=read(pp,['id','pickpoint2021_source_schedule_rows','pickpoint2021_distinct_exact_address_keys']).set_index('id');ff['pickpoint2021_distinct_operator_labels']=read(pp,['id','pickpoint2021_distinct_operator_labels']).set_index('id').iloc[:,0]
 ck('PickPoint_federal_exact_two_keys',len(ff)==2 and ff.index.is_unique and set(ff.index)=={'RU-FED-MOW','RU-FED-SPB'})
 for c,stat in [('pickpoint2021_source_schedule_rows',tab.groupby('federal').size()),('pickpoint2021_distinct_exact_address_keys',tab.groupby('federal').address_key.nunique()),('pickpoint2021_distinct_operator_labels',tab.groupby('federal').operator.nunique())]:ck('all_federal_'+c,np.array_equal(stat.reindex(ff.index,fill_value=0),ff[c]))
 # Read the two appended rows only, never a full ordinary914-field frame.
 ext=N/'core/feature_master_extended142572.parquet';meta=pq.ParquetFile(ext);ck('extended142572_metadata_rows',meta.metadata.num_rows==142572);fids=['RU-FED-MOW','RU-FED-SPB'];criteria=[('id','in',fids)];names=meta.schema_arrow.names;external={}
 wanted=[c for c in names if c.startswith(('econ_native_','econ_legacy_federal_','wb_federal_address_','places_federal_explicit_')) or c in ['name','region','lat','lon','axis_kind','settlement_identity_asserted','population_2002','population_2010','population_2021']]
 for i in range(0,len(wanted),2):
  d=read(ext,['id']+wanted[i:i+2],filters=criteria).set_index('id');ck('two_federal_ids_chunk'+str(i),set(d.index)==set(fids) and len(d)==2)
  for c in d:external[c]=d[c]
 for c in wanted:
  if c.startswith('econ_native_'):ck('federal_native_unknown_'+c,external[c].isna().all())
 ax=read(B/'anchor_research_20261019/data/external_federal_axis.csv')
 for row in ax.itertuples(index=False):ck('federal_population_'+row.territory_key+'_'+str(row.census_year),same(external['population_'+str(row.census_year)][row.territory_key],row.territory_population))
 for uid0 in fids:ck('federal_not_individual_settlement_'+uid0,external['axis_kind'][uid0]=='federal_city_territory_aggregate' and external['settlement_identity_asserted'][uid0]==False)
 for year in [2016,2021]:
  p=B/f'anchor_research_20261019/economy/federal_results/{year}/federal_legal_territory_features.parquet';schema=pq.ParquetFile(p).schema_arrow.names;data=read(p,['id','quality_mode'])
  for c in schema:
   if c in ['id','year','quality_mode']:continue
   d=read(p,['id','quality_mode',c])
   for r in d.itertuples(index=False,name=None):ck(f'federal_legacy_{year}_{r[0]}_{r[1]}_{c}',same(external[f'econ_legacy_federal_{year}_{r[1]}_{c}'][r[0]],r[2]))
 po=N/'places/places_objects_and_crosswalk.parquet';scope=['external_moscow_explicit_source_address','external_saint_petersburg_explicit_source_address'];places=read(po,['source_geography_scope','function_group','source_operating_status'],filters=[('source_geography_scope','in',scope)]);families=['school','preschool','other_education','hospital','healthcare','veterinary','pharmacy','bank','atm','post_office','postal_collection_point','market','retail_store','food_service','unknown_999','outside_requested_functions'];counts_out=[]
 for uid0,city in [('RU-FED-MOW','moscow'),('RU-FED-SPB','saint_petersburg')]:
  z=places[places.source_geography_scope.eq(f'external_{city}_explicit_source_address')];nc=z[~z.source_operating_status.isin(['permanently_closed','temporarily_closed'])];req=nc[~nc.function_group.isin(['unknown_999','outside_requested_functions'])];expected={'all_categories_count':len(z),'requested_function_count':len(req),'requested_function_diversity':req.function_group.nunique()};expected.update({f+'_count':int(nc.function_group.eq(f).sum()) for f in families});expected.update({'operating_'+st+'_count':int(z.source_operating_status.fillna('unknown').eq(st).sum()) for st in ['open','permanently_closed','unknown']})
  for c,v in expected.items():ck(uid0+'_Places_explicit_'+c,same(external['places_federal_explicit_'+c][uid0],v))
  counts_out.append({'id':uid0,**expected})
 for signal in ['fap','school','market','ozon','wildberries']:
  d=read(po,['source_geography_scope','source_operating_status','name_signal_'+signal],filters=[('source_geography_scope','in',scope)])
  for uid0,city in [('RU-FED-MOW','moscow'),('RU-FED-SPB','saint_petersburg')]:
   ix=d.source_geography_scope.eq(f'external_{city}_explicit_source_address')&~d.source_operating_status.isin(['permanently_closed','temporarily_closed']);ck(uid0+'_Places_explicit_name_'+signal,same(external['places_federal_explicit_name_signal_'+signal+'_count'][uid0],int(d.loc[ix,'name_signal_'+signal].sum())))
 pd.DataFrame(counts_out).to_csv(H/'independent_federal_places_explicit_counts.csv',index=False);ck('all_inputs_unchanged',all(sha(Path(p))==v for p,v in inputs.items()));summary={'PickPoint_source_rows':len(source),'ordinary_rows':ordinary_count,'ordinary_UIDs':int(uid.nunique()),'federal_rows':fedcount,'ambiguous_rows':ambiguous,'unresolved_rows':unresolved,'all505_federal_addresses_explicit_city':bool(fr.explicit_city_segment.all()),'extended_rows':meta.metadata.num_rows,'maximum_columns_read_per_Parquet_call':maxcols};result={'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','summary':summary,'checks':checks,'input_SHA256':inputs,'code_SHA256':sha(Path(__file__)),'limits':'Frozen selected2021 schedule rows, not complete physical operator network; explicit federal city strings with coarse oblast source headings, not independently verified legal polygons. Exact names/types do not prove service catchments. Ordinary914 master and closed validation package not modified.'};(H/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],len(checks),'checks',summary,flush=True);assert all(c['pass'] for c in checks)
if __name__=='__main__':main()
