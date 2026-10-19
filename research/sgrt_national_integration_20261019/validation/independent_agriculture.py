#!/usr/bin/env python3
"""Independent national agricultural join audit from the original 8.8M rows.

No import of the agriculture author's extraction or classification code.
Uses native municipal identity; never allocates hectares to settlement output.
"""
from pathlib import Path
import re,json,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;N=H.parent;B=N.parent;O=H/'independent_sources/agriculture';O.mkdir(parents=True,exist_ok=True)
GROUPS=['grain','technical','fodder','potato','vegetables','melon']
LABELS={'зерновые и зернобобовые культуры всего':'grain','технические культуры всего':'technical','кормовые культуры всего':'fodder','картофель':'potato','овощи без высадков':'vegetables','овощи всего':'vegetables','бахчевые продовольственные культуры':'melon','вся посевная площадь':'total','сельскохозяйственные культуры всего':'total'}
def label(s):return re.sub(r'[^а-яa-z0-9]+',' ',str(s).lower().replace('ё','е')).strip()
def code(s):
 z=s.astype('string').str.strip();return z.where(z.str.fullmatch(r'\d{7,8}',na=False)).str.zfill(8)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 checks=[]
 def ck(n,v,detail=None):checks.append({'name':n,'pass':bool(v),'detail':detail})
 rawpath=B/'restored/extracted/inputs/recovery_inputs/columnar/agriculture.parquet';chunks=[];scanned=0
 for batch in pq.ParquetFile(rawpath).iter_batches(batch_size=100000,columns=['oktmo','year','indicator_code','indicator_value','indicator_unit','kategor','kultur','mun_level','municipality','region_name']):
  d=batch.to_pandas();scanned+=len(d);d=d[d.mun_level.eq('Муниципальное образование верхнего уровня')&d.kategor.eq('Хозяйства всех категорий')&d.indicator_code.isin(['Y48007010','Y48007018'])&d.year.between(2006,2024)].copy();d['group']=d.kultur.map(label).map(LABELS);d.loc[d.indicator_code.eq('Y48007010'),'group']='production';d=d[d.group.notna()];d['oktmo']=code(d.oktmo);chunks.append(d)
 raw=pd.concat(chunks,ignore_index=True);raw.to_parquet(O/'independent_selected_raw.parquet',index=False);ck('original_raw_rows_scanned',scanned==8832750)
 frozen=pd.read_parquet(B/'restored/extracted/research/sgrt_recovered_20261019/agriculture/municipal_series_2006_2024.parquet')
 ck('selected_raw_count',len(raw)==len(frozen)==243202,{'independent':len(raw),'frozen':len(frozen)})
 cols=['oktmo','year','group','indicator_code','indicator_unit','indicator_value'];ra=raw[cols].sort_values(cols[:-1]+['indicator_value'],na_position='first').reset_index(drop=True);fa=frozen[cols].copy();fa.oktmo=code(fa.oktmo);fa=fa.sort_values(cols[:-1]+['indicator_value'],na_position='first').reset_index(drop=True)
 try:pd.testing.assert_frame_equal(ra,fa,check_dtype=False,check_exact=True);equal=True
 except AssertionError:equal=False
 ck('all_selected_raw_values_match_frozen_extract',equal)
 dup=raw.duplicated(['oktmo','year','group'],keep=False);ck('all_duplicate_claims_quarantined',int(dup.sum())==4260);clean=raw[~dup].copy();wide=clean[clean.group.ne('production')].pivot(index=['oktmo','year'],columns='group',values='indicator_value').reindex(columns=['total']+GROUPS).reset_index()
 values=wide[GROUPS];summed=values.sum(axis=1,min_count=1);negative=wide.total.lt(0)|values.lt(0).any(axis=1);over=summed>wide.total+np.maximum(1e-8,wide.total.abs()*.02);positive_at_zero=wide.total.eq(0)&values.gt(0).any(axis=1);bad=negative|over|positive_at_zero
 denom=wide.total.where(wide.total.gt(0));shares=values.div(denom,axis=0);dominance=shares.max(axis=1).fillna(0);dominant=shares.fillna(0).idxmax(axis=1);known_share=values.sum(axis=1).div(denom).fillna(0);profile=pd.Series('missing',index=wide.index,dtype='string')
 usable=~bad&wide.total.notna();profile.loc[usable&wide.total.eq(0)]='zero_sown';major=usable&wide.total.gt(0)&dominance.ge(.5);profile.loc[major]=dominant[major];mixed=usable&wide.total.gt(0)&~major&values.notna().all(axis=1)&known_share.ge(.9);profile.loc[mixed]='mixed'
 maximum=values.max(axis=1);largest_tie=values.eq(maximum,axis=0).sum(axis=1).gt(1)&maximum.gt(0);ties=major&largest_tie;profile.loc[ties]='ambiguous';wide['profile']=profile;wide['inconsistent']=bad;wide['dominance_tie']=ties;wide['largest_observed_group_tie']=largest_tie;wide['dominant_group']=values.fillna(-np.inf).idxmax(axis=1).mask(largest_tie|maximum.isna()|maximum.le(0)|bad|wide.total.isna()|wide.total.le(0));wide['equally_dominant_profiles']=['|'.join(g for g in GROUPS if row[g]==maximum.loc[i]) if ties.loc[i] else pd.NA for i,row in values.iterrows()]
 wide['equally_dominant_profiles']=wide.equally_dominant_profiles.fillna('');wide['dominant_group_informative']=wide.dominant_group.notna()
 author=pd.read_parquet(N/'agriculture/municipal_crop_annual_profiles.parquet').set_index(['oktmo','year']);w=wide.set_index(['oktmo','year']);ck('all_annual_native_keys',set(w.index)==set(author.index));author=author.reindex(w.index)
 for c in ['total']+GROUPS+['profile','inconsistent','dominance_tie','largest_observed_group_tie','dominant_group','dominant_group_informative','equally_dominant_profiles']:
  try:pd.testing.assert_series_equal(w[c],author[c],check_names=False,check_dtype=False,check_exact=True);ok=True
  except AssertionError:ok=False
  ck('annual_raw_recalculation_'+c,ok)
 ck('annual_rows',len(w)==38773)
 axis=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet');axis['native_code']=code(axis.municipality_oktmo8_2021);points=pd.read_parquet(N/'agriculture/point_municipal_agriculture.parquet').set_index('id').reindex(axis.id);axis=axis.set_index('id');ck('point_full_unique_axis',len(points)==142570 and points.index.is_unique)
 by2021=wide[wide.year.eq(2021)].set_index('oktmo');matched=axis.native_code.isin(set(clean.oktmo));ck('native_municipal_match_all_points',np.array_equal(matched.to_numpy(),points.agri_municipality_series_matched.to_numpy()));ck('native_municipal_key_all_points',axis.native_code.fillna('').equals(points.agri_municipality_code.fillna('')))
 for c in ['total']+GROUPS:
  expected=axis.native_code.map(by2021[c]);target='agri_total_ha_2021' if c=='total' else 'agri_'+c+'_ha_2021';ck('point_2021_'+c,np.allclose(expected.to_numpy(float),points[target].to_numpy(float),equal_nan=True,rtol=0,atol=1e-10))
 expected=axis.native_code.map(by2021.profile);ck('point_profile_all_points',expected.fillna('').eq(points.agri_municipal_profile_2021.fillna('')).all());valid=expected.notna()&expected.ne('missing');ck('covered2021_all_points',np.array_equal(valid.to_numpy(),points.agri_profile2021_covered.to_numpy()));ck('covered2021_count',int(valid.sum())==125109)
 # Last observed native-code crop and production years are not causal predictors
 # of earlier census changes, and may differ from last valid classification.
 latest=wide[wide.total.notna()].sort_values('year').drop_duplicates('oktmo',keep='last').set_index('oktmo');lastvalid=wide[~wide.profile.isin(['missing','ambiguous'])].sort_values('year').drop_duplicates('oktmo',keep='last').set_index('oktmo');prod=clean[clean.group.eq('production')&clean.indicator_value.notna()&clean.indicator_value.ge(0)].sort_values('year').drop_duplicates('oktmo',keep='last').set_index('oktmo')
 for source,col,target in [(latest,'year','agri_latest_crop_year'),(latest,'total','agri_latest_crop_total_ha'),(lastvalid,'year','agri_latest_valid_profile_year'),(prod,'year','agri_latest_production_year'),(prod,'indicator_value','agri_latest_production_nominal_thousand_rub')]:
  expected=axis.native_code.map(source[col]);ck('point_last_'+target,np.allclose(expected.to_numpy(float),points[target].to_numpy(float),equal_nan=True,rtol=0,atol=1e-10))
 for y in [2010,2021]:
  ps=clean[clean.group.eq('production')&clean.year.eq(y)].set_index('oktmo').indicator_value;expected=axis.native_code.map(ps);ck('point_production_'+str(y),np.allclose(expected.to_numpy(float),points[f'agri_production_nominal_thousand_rub_{y}'].to_numpy(float),equal_nan=True,rtol=0,atol=1e-10))
 # Preserve reason-specific national conflicts; tied dominant groups are a
 # separate review risk, not a silently invented crop class.
 review=wide[bad].copy();review['negative']=negative[bad];review['group_sum_exceeds_total_tolerance']=over[bad];review['positive_group_at_zero_total']=positive_at_zero[bad];review['linked_point_count']=review.oktmo.map(axis.native_code.value_counts()).fillna(0).astype(int);review.to_csv(O/'municipal_profile_conflicts.csv',index=False)
 wide[ties].to_csv(O/'dominance_tie_review.csv',index=False);ck('five_classification_ties_are_ambiguous',int(ties.sum())==5 and profile[ties].eq('ambiguous').all());ck('diagnostic_positive_maximum_ties',int(largest_tie.sum())==77)
 summary={'raw_rows_scanned':scanned,'selected_records':len(raw),'duplicate_records_quarantined':int(dup.sum()),'native_annual_profiles':len(wide),'matched_UIDs':int(matched.sum()),'valid2021_UIDs':int(valid.sum()),'unmatched_UIDs':int((~matched).sum()),'inconsistent2021_UIDs':int(axis.native_code.map(by2021.inconsistent).fillna(False).sum()),'native_annual_dominance_ties':int(ties.sum())}
 result={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','summary':summary,'checks':checks,'sources':{'raw_agriculture_sha256':sha(rawpath),'axis_sha256':sha(B/'anchor_research_20261019/data/point_axis.parquet'),'point_layer_sha256':sha(N/'agriculture/point_municipal_agriculture.parquet')},'independent_code_sha256':sha(Path(__file__)),'interpretation':'Independent extraction and aggregation of native municipal context. Repetition across settlement rows is not observed settlement production or agroservice attraction.'};(O/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':result['status'],'summary':summary,'checks':len(checks)},ensure_ascii=False),flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()
