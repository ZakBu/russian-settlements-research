"""Reconcile old eight-year reference2002 artifact with seven genuinely rerun annual years.
This does not project old aggregates onto the fresh2010 model.
"""
import pathlib,argparse,json,hashlib,os,pandas as pd,numpy as np
P=pathlib.Path(__file__).resolve().parent;ap=argparse.ArgumentParser();ap.add_argument('--missing',type=pathlib.Path,required=True);a=ap.parse_args();old=P/'reference2002_recovered';O=P/'reference2002_complete';O.mkdir(exist_ok=True);checks=[]
def ck(n,v):assert v,n;checks.append(dict(check=n,passed=True))
def save(d,n):
 for ext in ['parquet','csv.gz']:
  dest=O/(n+'.'+ext);tmp=O/(n+'.'+ext+'.tmp')
  if ext=='parquet':d.to_parquet(tmp,index=False);back=pd.read_parquet(tmp)
  else:d.to_csv(tmp,index=False,compression='gzip');back=pd.read_csv(tmp,compression='gzip')
  ck(n+' '+ext+' readback shape',back.shape==d.shape)
  for c in d.select_dtypes(include=[np.number]).columns:ck(n+' '+ext+' readback '+c,np.allclose(d[c],back[c],equal_nan=True))
  os.replace(tmp,dest)
receipts=[];sets=[]
for directory,epoch in [(old,'original_completed_cloud_run_recovered_and_reaudited'),(a.missing,'recovery_cloud_run_39221245465_recomputed')]:
 r=json.loads((directory/'coverage_provenance.json').read_text());sets.append({x['year'] for x in r});receipts.extend(dict(x,calculation_epoch=epoch) for x in r)
ck('annual sets disjoint',not sets[0]&sets[1]);ck('all15 years',sets[0]|sets[1]==set(range(2011,2026)));tree={int(x['path'].split('year=')[1].split('/')[0]):x for x in json.loads((P/'hf_tree.txt').read_text()) if x['path'].endswith('.parquet')};rows=[]
for r in sorted(receipts,key=lambda x:x['year']):
 y=r['year'];v=r['coverage'];ck(f'{y} success',r['status']=='ok');ck(f'{y} pinned source SHA',r['source_sha256']==tree[y]['lfs']['oid']);ck(f'{y} source byte count',r['bytes_transferred']==tree[y]['size']);ck(f'{y} rows match schema',v['rows']==r['schema_rows']);ck(f'{y} worker INN uniqueness assertion',v.get('inn_duplicates',0)==0);ck(f'{y} complete schema before rows',len(r['schema_columns'])==223 and r['footer_bytes']>0)
 if y<2014:ck(f'{y} coordinates absent',v['valid_coordinates']==0 and v['assigned']==0 and v['baseline_n']==0)
 rows.append(dict(year=y,status='processed',source_rows=r['schema_rows'],source_geocoded_rows=v['valid_coordinates'],spatial_assigned=v['assigned'],baseline_n=v['baseline_n'],strict_house_nonimputed_n=v['strict_house_nonimputed_n'],source_sha256=r['source_sha256'],source_bytes=r['bytes_transferred'],calculation_epoch=r['calculation_epoch'],spatial_coverage_status='no_coordinates_in_source' if y<2014 else 'spatially_observable_registered_addresses'))
frames={}
for name,keys in [('zone_financial',['center_id','year','selection']),('zone_sectors',['center_id','year','okved_section']),('localfirst_financial',['center_id','year','max_distance_km','quality']),('localfirst_sectors',['center_id','year','okved_section'])]:
 d=pd.concat([pd.read_parquet(old/(name+'.parquet')),pd.read_parquet(a.missing/(name+'.parquet'))],ignore_index=True);ck(name+' key uniqueness',not d.duplicated(keys).any());frames[name]=d;save(d,name)
f=frames['zone_financial'];s=frames['zone_sectors'];lf=frames['localfirst_financial'];ls=frames['localfirst_sectors'];allowed=set(pd.read_csv(P/'cloud_centers.csv').id);ck('flat reference IDs',set(f.center_id)<=allowed);allowed=set(pd.read_parquet(P/'cloud_localfirst_points.parquet').center_id.dropna());ck('LF reference IDs',set(lf.center_id)<=allowed)
for r in receipts:
 y=r['year'];v=r['coverage']
 for q in ['baseline','strict_house_nonimputed','house_or_street','all_outliers_included']:
  z=f[(f.year==y)&(f.selection==q)];ck(f'{y} {q} count audit',z.n_organizations.sum()==v[q+'_n']);ck(f'{y} {q} revenue audit',np.isclose(z.revenue_thousand_rub_nominal.sum(),v[q+'_revenue']))
 z=s[s.year==y];base=f[(f.year==y)&(f.selection=='baseline')];ck(f'{y} sector count global',z.n_organizations.sum()==base.n_organizations.sum());ck(f'{y} sector money global',np.isclose(z.revenue_thousand_rub_nominal.sum(),base.revenue_thousand_rub_nominal.sum()))
 if y>=2014:
  z=z.groupby(['center_id','year']).agg(n=('n_organizations','sum'),rv=('revenue_thousand_rub_nominal','sum')).reset_index();j=base.merge(z,on=['center_id','year'],how='outer',validate='one_to_one',indicator=True);ck(f'{y} each zone sector/financial present',j['_merge'].eq('both').all());ck(f'{y} each zone sector count',j.n_organizations.eq(j.n).all());ck(f'{y} each zone sector revenue',np.allclose(j.revenue_thousand_rub_nominal,j.rv,rtol=1e-11,atol=1e-4))
 for q in ['baseline','strict']:
  for dist in [1,5,10]:
   z=lf[(lf.year==y)&(lf.quality==q)&(lf.max_distance_km==dist)];ck(f'{y} LF{q}{dist} count audit',z.n_organizations.sum()==v[f'localfirst_{q}_{dist}km_n']);ck(f'{y} LF{q}{dist} money audit',np.isclose(z.revenue_thousand_rub_nominal.sum(),v[f'localfirst_{q}_{dist}km_revenue']))
 z=ls[ls.year==y];base=lf[(lf.year==y)&(lf.quality=='baseline')&(lf.max_distance_km==5)];ck(f'{y} LF sector count',z.n_organizations.sum()==base.n_organizations.sum());ck(f'{y} LF sector money',np.isclose(z.revenue_thousand_rub_nominal.sum(),base.revenue_thousand_rub_nominal.sum()))
status=pd.DataFrame(rows);save(status,'year_status');(O/'source_provenance.json').write_text(json.dumps(receipts,indent=2));(O/'verification.json').write_text(json.dumps(dict(passed=True,n_checks=len(checks),source_organization_year_rows=int(status.source_rows.sum()),all15_statuses_processed=bool(status.status.eq('processed').all()),geometry='Frozen reference2002 only; not fresh nearest2010',checks=checks),indent=2));(O/'FINISHED.json').write_text(json.dumps(dict(geometry='reference2002',outputs=[dict(name=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(O.glob('*')) if p.is_file() and not p.name.endswith('.tmp') and p.name!='FINISHED.json']),indent=2));print('PASS',len(checks),'all15reference checks',int(status.source_rows.sum()),'source organization-years',flush=True)
