#!/usr/bin/env python3
"""Independent audit: no import of author model or preprocessing modules.

Raw RFSD column projection; relational merge/groupby, not author bit masks/bincount.
Medical parsing uses independent token regex. Temporal accounting uses membership
matrices. Geographic resampling uses equal-area kilometre squares and offsets.
"""
from pathlib import Path
import hashlib, json, re
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT.parent; OUT=Path(__file__).resolve().parent
CHECKS=[]; INPUTS={}; COUNTERS={}
GROUPS={'retail47':('G',{'47'}),'food56':('I',{'56'}),'education85':('P',{'85'}),
 'health86':('Q',{'86'}),'social8788':('Q',{'87','88'}),'repair95':('S',{'95'}),
 'personal96':('S',{'96'}),'accommodation55':('I',{'55'}),'finance64to66':('K',{'64','65','66'}),'admin84':('O',{'84'})}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def freeze(p): INPUTS[str(p.relative_to(BASE))]={'sha256':sha(p),'bytes':p.stat().st_size};return p
def check(name,condition,detail=None):
 CHECKS.append({'name':name,'pass':bool(condition),'detail':detail})
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def norm(s):
 z=s.astype('string').str.strip();return z.where(z.str.fullmatch('[0-9]{10,11}',na=False)).str.zfill(11)

def raw_read(year,axis):
 f=freeze(BASE/f'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_{year}_selected.parquet')
 d=pd.read_parquet(f,columns=['inn','oktmo','okved','okved_section','filed'])
 valid=d.inn.astype('string').str.fullmatch('[0-9]{10}',na=False)
 COUNTERS[f'invalid_inn_{year}']=int((~valid).sum());d=d[valid].copy()
 check(f'unique_valid_inn_{year}',not d.inn.duplicated().any())
 d['code']=norm(d.oktmo);d['id']=d.code.map(axis.set_index('code').id)
 # Distinguish unrecognised/old-prefix section combinations instead of silently
 # treating them as proof of an absent physical function.
 d['prefix']=d.okved.astype('string').str.extract(r'^(\d{2})',expand=False)
 for g,(section,prefixes) in GROUPS.items():
  d[g]=(d.okved_section.eq(section)&d.prefix.isin(prefixes)).fillna(False)
 known_pairs=set((sec,p) for sec,ps in GROUPS.values() for p in ps)
 diag=d.groupby(['okved_section','prefix'],dropna=False).size().reset_index(name='n')
 diag['matches_study_function']=diag.apply(lambda r:(r.okved_section,r.prefix) in known_pairs,axis=1)
 diag.to_csv(OUT/f'okved_section_prefix_{year}.csv',index=False)
 COUNTERS[f'valid_INN_{year}']=len(d)
 print('Independent raw read',year,len(d),flush=True)
 return d[['inn','id','filed','prefix','okved_section']+list(GROUPS)]

def point_counts(d,axis):
 z=d.dropna(subset=['id']).groupby('id')[list(GROUPS)].sum().reindex(axis.id,fill_value=0)
 return z.astype('int64')

def economy(axis):
 raws={y:raw_read(y,axis) for y in (2016,2021)}
 a,b=raws[2016],raws[2021]
 common=a.merge(b,on='inn',suffixes=('_a','_b'),validate='one_to_one')
 both=common.id_a.notna()&common.id_b.notna();same=both&common.id_a.eq(common.id_b)
 stable=common.prefix_a.fillna('').eq(common.prefix_b.fillna(''))&common.okved_section_a.fillna('').eq(common.okved_section_b.fillna(''))
 filed=same&common.filed_a.eq(1)&common.filed_b.eq(1)
 COUNTERS.update({'common_INN':len(common),'only_2016_INN':len(a)-len(common),'only_2021_INN':len(b)-len(common),
  'common_exact_point_both':int(both.sum()),'common_same_exact_point':int(same.sum()),
  'common_different_exact_points':int((both&~same).sum()),'common_same_point_filed_both':int(filed.sum()),
  'common_same_point_unchanged_2digit_section':int((same&stable).sum()),'common_same_point_class_changed':int((same&~stable).sum())})
 reported=json.loads(freeze(ROOT/'economy/results/cohort_audit.json').read_text())
 for k,v in COUNTERS.items():
  if k in reported:check('raw_cohort_'+k,v==reported[k],{'independent':v,'author':reported[k]})
 author=pd.read_parquet(freeze(ROOT/'economy/results/point_cohort_sensitivity.parquet'))
 summaries=[];features={}
 for name,keep in [('all_exact_code',None),('common_INN_any_address',np.ones(len(common),bool)),('common_INN_same_exact_point',same),('common_INN_same_point_filed_both',filed),('common_INN_same_point_same_primary_code',same&stable)]:
  cs={}
  for y,suffix in [(2016,'a'),(2021,'b')]:
   if keep is None:dd=raws[y]
   else:dd=common.loc[keep,['id_'+suffix]+[g+'_'+suffix for g in GROUPS]].rename(columns={'id_'+suffix:'id',**{g+'_'+suffix:g for g in GROUPS}})
   cs[y]=point_counts(dd,axis)
   r=author[author.cohort.eq(name)].set_index('id').reindex(axis.id)
   for g in GROUPS:check(f'point_count_{name}_{y}_{g}',np.array_equal(cs[y][g].to_numpy(),r[f'{g}_{y}'].to_numpy()))
  da=(cs[2016][list(GROUPS)[:7]]>0).sum(axis=1).to_numpy();db=(cs[2021][list(GROUPS)[:7]]>0).sum(axis=1).to_numpy()
  features[name]=(da,db)
  for k in [1,2,3]:
   aa=da>=k;bb=db>=k
   summaries.append({'cohort':name,'threshold':k,'observed_2016':int(aa.sum()),'observed_2021':int(bb.sum()),'lost':int((aa&~bb).sum()),'gained':int((~aa&bb).sum()),'retained':int((aa&bb).sum()),'net':int(bb.sum()-aa.sum())})
 pd.DataFrame(summaries).to_csv(OUT/'independent_cohort_summary.csv',index=False)
 # Baseline aggregate pairing checked independently; the raw exact-code audit
 # above has a different implementation and is not dependent on these aggregates.
 agg={y:pd.read_parquet(freeze(BASE/f'anchor_research_20261019/economy/coded_results/{y}/points_economic_features.parquet')) for y in (2016,2021)}
 p=pd.read_parquet(freeze(ROOT/'economy/results/point_function_dynamics.parquet'))
 for mode in ['coded_baseline','coded_strict_house_5km']:
  aa=agg[2016][agg[2016].quality_mode.eq(mode)].set_index('id').reindex(axis.id)
  bb=agg[2021][agg[2021].quality_mode.eq(mode)].set_index('id').reindex(axis.id)
  pp=p[p.quality_mode.eq(mode)].set_index('id').reindex(axis.id)
  da=aa.direct_consumer_function_diversity.to_numpy();db=bb.direct_consumer_function_diversity.to_numpy();features[mode]=(da,db)
  check('paired_full_axis_'+mode,len(pp)==len(axis) and not pp.index.duplicated().any())
  for year,src in [(2016,aa),(2021,bb)]:
   for col in ['legal_entities','direct_consumer_function_diversity']+[g+'_legal_entities' for g in GROUPS]:
    check(f'paired_{mode}_{year}_{col}',np.array_equal(src[col],pp[f'{col}_{year}']))
  check('zero_population_preserved_'+mode,int(pp.population_2010.eq(0).sum())==int(axis.population_2010.eq(0).sum()))
  for k in [1,2,3]:
   x=da>=k;y=db>=k
   summaries.append({'cohort':mode,'threshold':k,'observed_2016':int(x.sum()),'observed_2021':int(y.sum()),'lost':int((x&~y).sum()),'gained':int((~x&y).sum()),'retained':int((x&y).sum()),'net':int(y.sum()-x.sum())})
 pd.DataFrame(summaries).to_csv(OUT/'independent_cohort_summary.csv',index=False)
 return features

def spatial(axis,features):
 # Local LAEA: equal-area square cells, NOT a road metric or constant shape.
 transformer=Transformer.from_crs('EPSG:4326','+proj=laea +lat_0=60 +lon_0=100 +datum=WGS84 +units=m',always_xy=True)
 x,y=transformer.transform(axis.lon.to_numpy(),axis.lat.to_numpy());rows=[]
 rng=np.random.default_rng(20261019)
 for km in [250,400,600]:
  for shift in [0,.5]:
   cells=pd.MultiIndex.from_arrays([np.floor(x/(km*1000)+shift).astype(int),np.floor(y/(km*1000)+shift).astype(int)])
   code,keys=pd.factorize(cells,sort=True);sizes=np.bincount(code);B=2000
   # Repeated selection weights complete cells; each point contributes one,
   # and numerator and denominator are jointly resampled.
   weights=rng.multinomial(len(keys),np.full(len(keys),1/len(keys)),size=B)
   for mode,(a,b) in features.items():
    for k in [1,2,3]:
     delta=(b>=k).astype(int)-(a>=k).astype(int);tot=np.bincount(code,weights=delta)
     reps=(weights@tot)/(weights@sizes);q=np.quantile(reps,[.025,.5,.975])
     rows.append(dict(cohort=mode,threshold=k,square_km=km,cell_shift_fraction=shift,n_blocks=len(keys),n=len(axis),net_count=int(delta.sum()),net_proportion=float(delta.mean()),composition_p025=float(q[0]),composition_p50=float(q[1]),composition_p975=float(q[2]),replications=B,seed=20261019,interpretation='geographic_composition_sensitivity_not_sampling_confidence_interval'))
     check(f'spatial_balance_{mode}_{k}_{km}_{shift}',sizes.sum()==len(axis) and int(tot.sum())==int(delta.sum()))
 pd.DataFrame(rows).to_csv(OUT/'equal_area_block_sensitivity.csv',index=False)

def history(axis):
 h=pd.read_csv(freeze(ROOT/'history/edges_by_year.csv'));reported=pd.read_csv(freeze(ROOT/'model/results/history_two_axis_accounting.csv'));p=axis.set_index('id');rows=[]
 for before,after in [(2023,2025),(2025,2026)]:
  a=h[h.year.eq(before)].set_index('origin_uid');b=h[h.year.eq(after)].set_index('origin_uid');u=a.index.intersection(b.index);a=a.loc[u];b=b.loc[u]
  changed=a.destination_uid.ne(b.destination_uid);COUNTERS[f'school_changed_{before}_{after}']=int(changed.sum())
  for dest in sorted(set(a.destination_uid)|set(b.destination_uid)):
   w0=a.destination_uid.eq(dest).to_numpy().astype(int);w1=b.destination_uid.eq(dest).to_numpy().astype(int)
   old=p.loc[u,'population_2010'].to_numpy();new=p.loc[u,'population_2021'].to_numpy()
   vals={'old_boundary_old_population':w0@old,'old_boundary_new_population':w0@new,'new_boundary_old_population':w1@old,'new_boundary_new_population':w1@new,'two_axis_total_difference':w1@new-w0@old,'fixed_old_boundary_population_change':w0@(new-old),'boundary_effect_at_new_population':(w1-w0)@new}
   z=reported[reported.from_document_year.eq(before)&reported.to_document_year.eq(after)&reported.destination_uid.eq(dest)].iloc[0]
   for k,v in vals.items():check(f'accounting_{before}_{after}_{dest}_{k}',v==z[k])
   check(f'accounting_identity_{before}_{after}_{dest}',vals['two_axis_total_difference']==vals['fixed_old_boundary_population_change']+vals['boundary_effect_at_new_population'])
   rows.append({'before':before,'after':after,'destination':p.loc[dest,'name'],**vals})
 pd.DataFrame(rows).to_csv(OUT/'independent_history_accounting.csv',index=False)

def medical():
 src=[]
 for year,stem in [(2025,'sv_tariff_2025_full'),(2026,'sv_tariff_2026')]:
  txt=freeze(ROOT/f'medical/captures/{stem}.txt').read_text()
  for line in txt.splitlines():
   m=re.match(r'^\s*(225|277)\s+Г[АБ]УЗ.*?\b(111\d{3,4})\b(.*)',line)
   if not m:continue
   # Staff flag and population occupy the five numeric fields immediately
   # before the independently printed population-size category.
   tail=m[3]; n=re.search(r'\s+([01])\s+([01])\s+([01])\s+(\d(?: ?\d)*)\s{2,}(\d(?: ?\d)*)\s{2,}\S',tail)
   if not n:raise ValueError('Independent tariff row failed: '+line)
   src.append({'year':year,'org':int(m[1]),'code':int(m[2]),'worker':int(n[2]),'fully_staffed':int(n[3]),'population':int(n[4].replace(' ',''))})
 d=pd.DataFrame(src);d.to_csv(OUT/'independent_tariff_snapshots.csv',index=False)
 author=pd.read_csv(freeze(ROOT/'medical/tariff_snapshots.csv'));author['year']=author.snapshot_date.str[:4].astype(int)
 z=d.merge(author,left_on=['year','org','code'],right_on=['year','organization_code','unit_code'],validate='one_to_one',how='outer',indicator=True)
 check('medical_all_49_raw_rows',len(z)==49 and z._merge.eq('both').all())
 for a,b in [('population','registered_population'),('worker','medical_worker_present'),('fully_staffed_x','fully_staffed_y')]:check('medical_raw_'+a,np.array_equal(z[a],z[b]))
 summary=d.groupby(['org','year']).agg(listed=('code','size'),staffed=('worker','sum'),population=('population','sum')).reset_index();summary.to_csv(OUT/'independent_medical_summary.csv',index=False)
 check('medical_no_negative_population',d.population.ge(0).all())
 pair=d[d.year.eq(2025)].merge(d[d.year.eq(2026)],on=['org','code'],suffixes=('_before','_after'),how='outer',indicator=True)
 check('medical_24_pairs_staff_unchanged',pair._merge.eq('both').sum()==24 and pair.loc[pair._merge.eq('both'),'worker_before'].eq(pair.loc[pair._merge.eq('both'),'worker_after']).all())
 absent=pair[pair._merge.eq('left_only')];check('medical_absent_row_zero_before',len(absent)==1 and absent.population_before.eq(0).all() and absent.worker_before.eq(0).all())

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 axis=pd.read_parquet(freeze(BASE/'anchor_research_20261019/data/point_axis.parquet'),columns=['id','name','lat','lon','population_2010','population_2021','oktmo_2021']);axis['code']=norm(axis.oktmo_2021)
 check('axis_complete_unique',len(axis)==142570 and axis.id.is_unique and axis.code.is_unique)
 medical();history(axis);features=economy(axis);spatial(axis,features)
 dump(OUT/'AUDIT.json',{'status':'PASS' if all(c['pass'] for c in CHECKS) else 'FAIL','checks':CHECKS,'n_checks':len(CHECKS),'counters':COUNTERS,'inputs':INPUTS,'independent_code_sha256':sha(Path(__file__)),'authorship':'Independent auditor. No input/model authorship; no imports of author modules.','limits':['RFSD legal registrations are not physical functions or flows','2016 OKVED version provenance remains necessary','Block intervals are geographic composition sensitivity, not census sampling uncertainty','Document and census dates are different axes']})
 print('Independent audit',len(CHECKS),'checks',all(c['pass'] for c in CHECKS),flush=True)
 assert all(c['pass'] for c in CHECKS)
if __name__=='__main__':main()
