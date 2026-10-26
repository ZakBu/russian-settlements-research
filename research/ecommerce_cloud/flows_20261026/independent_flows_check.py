"""Independent pandas recomputation from pinned KOUZh individual members.

Does not import primary analysis. Produces aggregates only, never respondent rows.
"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3]
RAW=ROOT/'work/ecommerce_flows_20261026'
OUT=ROOT/'work/ecommerce_flows_20261026/independent_review'
OUT.mkdir(exist_ok=True)
CATS=['food','clothing','appliances']
COLS=['H01_12','H01_01','H01_02','H00_04','KVZV','R_1_1','D03_23','D03_31','D03_32','D03_33','I07_05','I07_16']+[f'I04_0{n}_0{i}' for n in (3,4) for i in (1,2,3)]
results=[]; school=[]
for year in (2018,2022,2024):
 path=RAW/f'{year}_individual.csv'
 d=pd.read_csv(path,sep=';',dtype=str,usecols=COLS,keep_default_na=False)
 for col in d:
  d[col]=pd.to_numeric(d[col].str.strip().str.replace(',','.',regex=False),errors='coerce')
 assert d.KVZV.notna().all() and d.KVZV.gt(0).all()
 for loc,label in ((1,'urban_all'),(2,'rural_all')):
  roster=d.loc[d.H01_02.ge(15)&d.H00_04.eq(loc)]
  adults=roster.loc[roster.H01_12.ne(99)]
  for i,cat in enumerate(CATS,1):
   geo=adults[f'I04_03_0{i}']; remote=adults[f'I04_04_0{i}']; w=adults.KVZV
   row={'year':year,'group':label,'category':cat,'n_adults':len(adults),'weighted_adults':float(w.sum()),'n_roster':len(roster),'weighted_roster':float(roster.KVZV.sum()),'n_uninterviewed':int(roster.H01_12.eq(99).sum())}
   for code in (1,2,3,4,-7):
    mask=geo.eq(code); row[f'geo{code}_n']=int(mask.sum());row[f'geo{code}_weight']=float(w[mask].sum())
   for code in (1,2,3,4,-7):
    mask=remote.eq(code);row[f'remote{code}_n']=int(mask.sum());row[f'remote{code}_weight']=float(w[mask].sum())
   for lab,var in [('geo',geo),('remote',remote)]:
    mask=var.isna();row[f'{lab}_blank_n']=int(mask.sum());row[f'{lab}_blank_weight']=float(w[mask].sum())
    unknown=~var.isin([1,2,3,4,-7])&var.notna(); assert not unknown.any(),(year,lab)
   row['geo_home_pct_roster']=float(100*w[geo.eq(1)].sum()/roster.KVZV.sum())
   row['geo_home_pct_all']=float(100*w[geo.eq(1)].sum()/w.sum())
   row['geo_home_pct_valid']=float(100*w[geo.eq(1)].sum()/w[geo.isin([1,2,3,4])].sum())
   row['remote_any_pct_all']=float(100*w[remote.isin([1,2])].sum()/w.sum())
   for use,labeluse in [(remote.isin([1,2]),'remote_any'),(remote.isin([3,4]),'remote_no')]:
    row[f'{labeluse}_n']=int(use.sum());row[f'{labeluse}_weight']=float(w[use].sum())
    for code in (1,2,3,4,-7):
     mask=use&geo.eq(code);row[f'{labeluse}_geo{code}_n']=int(mask.sum());row[f'{labeluse}_geo{code}_weight']=float(w[mask].sum())
    row[f'{labeluse}_geo_home_pct']=float(100*w[use&geo.eq(1)].sum()/w[use].sum())
   results.append(row)
  c=d.loc[d.H01_02.between(7,14)&d.H00_04.eq(loc)&d.D03_23.eq(1)]
  w=c.KVZV; dest=c.D03_31; valid=dest.isin([1,2]); outside=dest.eq(2)
  row=dict(year=year,group=label,n_eligible=len(c),weighted_eligible=float(w.sum()),n_valid_location=int(valid.sum()),weighted_valid_location=float(w[valid].sum()),n_other_settlement=int(outside.sum()),weighted_other_settlement=float(w[outside].sum()),pct_other_all_eligible=float(100*w[outside].sum()/w.sum()),pct_other_valid=float(100*w[outside].sum()/w[valid].sum()),pct_missing=float(100*w[~valid].sum()/w.sum()))
  for m in (1,2,3,4,5):row[f'pct_mode{m}_among_other']=float(100*w[outside&c.D03_32.eq(m)].sum()/w[outside].sum())
  row['pct_mode_missing_among_other']=float(100*w[outside&~c.D03_32.isin([1,2,3,4,5])].sum()/w[outside].sum())
  timed=c.loc[outside&c.D03_33.ge(0)].sort_values('D03_33')
  cumulative=timed.KVZV.cumsum()
  row['weighted_median_minutes_other']=float(timed.loc[cumulative.ge(timed.KVZV.sum()/2),'D03_33'].iloc[0])
  row['n_time_valid_other']=len(timed)
  school.append(row)
  assert all(c.H01_02.between(7,14))
checks=0
# Independent row-based reweighting to the 2022 rural composition.
stratum_frames={}
for year in (2018,2022,2024):
 path=RAW/f'{year}_individual.csv'
 x=pd.read_csv(path,sep=';',usecols=['H01_02','H01_01','H01_12','R_1_1','H00_04','KVZV']+[f'I04_0{n}_0{i}' for n in (3,4) for i in (1,2,3)])
 x=x.loc[x.H01_02.ge(15)&x.H01_12.ne(99)&x.H00_04.eq(2)].copy()
 x['age']=pd.cut(x.H01_02,[14,29,44,59,np.inf],labels=[0,1,2,3]).astype(int)
 x['stratum']=list(zip(x.R_1_1.astype(int),x.age,x.H01_01.astype(int)))
 stratum_frames[year]=x
common=set.intersection(*(set(x.stratum) for x in stratum_frames.values()))
target=stratum_frames[2022].loc[lambda x:x.stratum.isin(common)].groupby('stratum').KVZV.sum()
target=target/target.sum()
standard=[]
for year,x in stratum_frames.items():
 x=x.loc[x.stratum.isin(common)].copy()
 mass=x.groupby('stratum').KVZV.sum()
 x['stdw']=x.KVZV*x.stratum.map(target)/x.stratum.map(mass)
 assert np.isclose(x.stdw.sum(),1)
 for i,cat in enumerate(CATS,1):
  standard.append(dict(year=year,category=cat,own_pct=100*x.loc[x[f'I04_03_0{i}'].eq(1),'stdw'].sum(),nearby_pct=100*x.loc[x[f'I04_03_0{i}'].eq(2),'stdw'].sum(),remote_pct=100*x.loc[x[f'I04_04_0{i}'].isin([1,2]),'stdw'].sum(),strata=len(common)))
(OUT/'shopping_standardised.json').write_text(json.dumps(standard,ensure_ascii=False,indent=2)+'\n')
reported=pd.read_csv(ROOT/'research/ecommerce_cloud/flows_20261026/school_locations.csv')
for row in school:
 match=reported.loc[reported.year.eq(row['year'])&reported.group.eq(row['group'])].iloc[0]
 for k,v in row.items():
  if k in ('year','group'):continue
  assert np.isclose(v,match[k],rtol=1e-10,atol=1e-7),(k,v,match[k]);checks+=1
manifest=json.loads((RAW/'acquisition_manifest.json').read_text())
for r in manifest:
 p=RAW/r['filename']
 assert p.stat().st_size==r['bytes']; assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];checks+=2
(OUT/'shopping_aggregates.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
(OUT/'school_aggregates.json').write_text(json.dumps(school,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'checks':checks,'shopping_rows':len(results),'school_groups':len(school),'raw_members':len(manifest),'rural_shopping':[r for r in results if r['group']=='rural_all'],'rural_school':[r for r in school if r['group']=='rural_all']},ensure_ascii=False))
# Compare the independently computed estimates to the finished primary tables.
primary=ROOT/'research/ecommerce_cloud/flows_20261026'
if (primary/'purchase_geography.csv').exists():
 goods={"food":"food_and_personal_hygiene","clothing":"clothing_and_footwear","appliances":"appliances_electronics_communications"}
 places={1:'own_locality_or_urban_district',2:'nearby_localities_or_districts',3:'other_russian_region',4:'abroad',-7:'dont_know'}
 table=pd.read_csv(primary/'purchase_geography.csv')
 joint=pd.read_csv(primary/'purchase_geography_by_remote_use.csv')
 stdtable=pd.read_csv(primary/'purchase_rural_standardised.csv')
 primary_checks=0
 for row in results:
  rr=table.loc[table.year.eq(row['year'])&table.goods.eq(goods[row['category']])&table.scope.eq('locality')&table.group.eq(row['group'].replace('_all',''))].iloc[0]
  assert rr.sample_n==row['n_adults'];primary_checks+=1
  assert np.isclose(rr.base_weight,row['weighted_adults']);primary_checks+=1
  assert np.isclose(rr.remote_any_pct,row['remote_any_pct_all']);primary_checks+=1
  assert np.isclose(rr.own_among_valid_pct,row['geo_home_pct_valid']);primary_checks+=1
  for code,label in places.items():
   assert rr[label+'_n']==row[f'geo{code}_n'];primary_checks+=1
   assert np.isclose(rr[label+'_weight'],row[f'geo{code}_weight']);primary_checks+=1
   assert np.isclose(rr[label+'_pct'],100*row[f'geo{code}_weight']/row['weighted_adults']);primary_checks+=1
  for grp,main in [('remote_any','remote_any'),('remote_no','no_remote')]:
   jj=joint.loc[joint.year.eq(row['year'])&joint.goods.eq(goods[row['category']])&joint.scope.eq('remote_group_'+row['group'].replace('_all',''))&joint.group.eq(main)].iloc[0]
   assert jj.sample_n==row[grp+'_n'];primary_checks+=1
   assert np.isclose(jj.base_weight,row[grp+'_weight']);primary_checks+=1
   for code,label in places.items():
    assert jj[label+'_n']==row[f'{grp}_geo{code}_n'];primary_checks+=1
    assert np.isclose(jj[label+'_weight'],row[f'{grp}_geo{code}_weight']);primary_checks+=1
 for row in standard:
  rr=stdtable.loc[stdtable.year.eq(row['year'])&stdtable.goods.eq(goods[row['category']])].iloc[0]
  for own,main in [('own_pct','own_locality_or_urban_district_pct'),('nearby_pct','nearby_localities_or_districts_pct'),('remote_pct','remote_any_pct')]:
   assert np.isclose(row[own],rr[main],rtol=1e-10);primary_checks+=1
 print(json.dumps({'primary_shopping_checks':primary_checks,'primary_shopping_discrepancies':0},ensure_ascii=False))
if (primary/'purchase_groups_standardised2024.csv').exists():
 gg=pd.read_csv(primary/'purchase_groups_standardised2024.csv');gc=0
 x=stratum_frames[2024]
 for i,cat in enumerate(CATS,1):
  remote=x[f'I04_04_0{i}']; eligible=x.loc[remote.isin([1,2,3,4])].copy()
  eligible['remote_grp']=np.where(eligible[f'I04_04_0{i}'].isin([1,2]),'remote_any','no_remote')
  group_sets=[set(z.stratum) for _,z in eligible.groupby('remote_grp')]
  common_group=set.intersection(*group_sets)
  target=eligible.loc[eligible.stratum.isin(common_group)].groupby('stratum').KVZV.sum();target=target/target.sum()
  for group,z in eligible.groupby('remote_grp'):
   z=z.loc[z.stratum.isin(common_group)].copy();mass=z.groupby('stratum').KVZV.sum()
   z['rw']=z.KVZV*z.stratum.map(target)/z.stratum.map(mass)
   value=100*z.loc[z[f'I04_03_0{i}'].eq(1),'rw'].sum()
   rr=gg.loc[gg.goods.eq(goods[cat])&gg.remote_group.eq(group)].iloc[0]
   assert np.isclose(value,rr.standardised_own_pct,rtol=1e-10);gc+=1
 print(json.dumps({'primary_crossgroup_standardised_checks':gc,'discrepancies':0},ensure_ascii=False))
