"""Read back the national join and test accounting and evidence separation."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
R=Path(__file__).resolve().parent;B=R.parents[1]
p=pd.read_parquet(R/'point_municipal_agriculture.parquet');m=pd.read_parquet(R/'municipal_agriculture_snapshot.parquet');a=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet');checks=[]
def ck(n,v):checks.append({'name':n,'pass':bool(v)})
ck('all_UIDs_once',len(p)==142570 and p.id.is_unique and set(p.id)==set(a.id))
ck('all_nonkey_fields_namespaced',all(c=='id' or c.startswith('agri_') for c in p))
ck('municipal_key_unique',m.municipality_code.is_unique)
f=pd.read_csv(B/'restored/extracted/research/sgrt_recovered_20261019/agriculture/municipal_crop_profiles_2021.csv',dtype={'oktmo':str});f['oktmo']=f.oktmo.str.zfill(8)
j=p[['id','agri_municipality_code','agri_total_ha_2021','agri_municipal_profile_2021']].merge(f[['oktmo','total','municipal_profile']],left_on='agri_municipality_code',right_on='oktmo',how='left',validate='many_to_one')
ck('all2021_totals_equal_frozen_source',np.allclose(j.agri_total_ha_2021,j.total,equal_nan=True))
ck('all2021_profile_labels_equal_frozen_source',j.agri_municipal_profile_2021.fillna('__NULL__').eq(j.municipal_profile.fillna('__NULL__')).all())
native=a[['id','municipality_oktmo8_2021']].copy();native['code']=native.municipality_oktmo8_2021.astype('string').str.zfill(8);q=p.merge(native,on='id',validate='one_to_one');ck('native_code_no_nearest_override',q.agri_municipality_code.fillna('').eq(q.code.fillna('')).all())
ck('no_direct_point_measurement_claim',not p.agri_point_agriculture_observed.any())
ck('no_direct_flow_claim',not p.agri_actual_agroservice_flow_observed.any())
ck('no_historical_boundary_equivalence_claim',not p.agri_historical_boundary_equivalence_proven.any())
statuses=p.agri_area_evidence_status_2021.value_counts().to_dict();ck('evidence_partition142570',sum(statuses.values())==len(p))
ck('no_zero_missing_conflation',not (p.agri_observed_zero_area_2021 & p.agri_total_ha_2021.isna()).any())
ck('positive_municipal_context133569',p.agri_observed_positive_area_2021.sum()==133569)
ck('knownzero_municipal_context0',p.agri_observed_zero_area_2021.sum()==0)
ck('full_coverage_accounting',p.agri_municipality_series_matched.sum()==142525 and (~p.agri_municipality_series_matched).sum()==45)
ck('one_upstream_parent_ambiguity',p.agri_bridge_ambiguous.sum()==1)
ck('strict_sensitivity142524',int((p.agri_municipality_series_matched&~p.agri_bridge_ambiguous).sum())==142524)
ck('strict_valid_profiles125108',int((p.agri_profile2021_covered&~p.agri_bridge_ambiguous).sum())==125108)
cols=['total_ha_2021','grain_ha_2021','technical_ha_2021','fodder_ha_2021','potato_ha_2021','vegetables_ha_2021','melon_ha_2021','latest_crop_total_ha','latest_production_nominal_thousand_rub','total_ha_2010_native_code','production_nominal_thousand_rub_2010','production_nominal_thousand_rub_2021']
linked=p[p.agri_municipality_series_matched].drop_duplicates('agri_municipality_code');source=m[m.municipality_code.isin(linked.agri_municipality_code)]
for c in cols:ck('unique_municipality_mass_'+c,np.isclose(linked['agri_'+c].sum(min_count=1),source[c].sum(min_count=1),equal_nan=True))
coverage=pd.read_csv(R/'coverage_by_region.csv');ck('regional_sums',int(coverage.points.sum())==len(p) and int(coverage.matched.sum())==142525)
x=pd.read_parquet(R/'municipal_crop_annual_profiles.parquet')
expected={('17720000',2015),('58701000',2022),('82700000',2024),('98606000',2022),('98642000',2016)}
ck('five_regression_tie_keys',set(zip(x.loc[x.dominance_tie,'oktmo'],x.loc[x.dominance_tie,'year']))==expected)
ck('classification_ties_ambiguous_and_group_unknown',x.loc[x.dominance_tie,'profile'].eq('ambiguous').all() and x.loc[x.dominance_tie,'dominant_group'].isna().all())
ck('2021_no_classification_ties',not x.loc[x.year.eq(2021),'dominance_tie'].any())
ck('latest_valid_excludes_ambiguous',not m.latest_valid_profile.isin(['missing','ambiguous']).any())
tiejoin=p[['agri_municipality_code','agri_latest_crop_dominance_tie']].merge(m[['municipality_code','latest_crop_dominance_tie']],left_on='agri_municipality_code',right_on='municipality_code',how='left',validate='many_to_one')
ck('point_latest_tie_matches_municipal_source',tiejoin.agri_latest_crop_dominance_tie.fillna(False).eq(tiejoin.latest_crop_dominance_tie.astype('boolean').fillna(False)).all())
groups=['grain','technical','fodder','potato','vegetables','melon'];maxknown=x[groups].max(axis=1)
invalid=x.total.isna()|x.total.le(0)|x.inconsistent|maxknown.isna()|maxknown.le(0)|x.largest_observed_group_tie
ck('no_annual_dominant_group_when_uninformative',x.loc[invalid,'dominant_group'].isna().all())
ck('annual_informative_flag_exact',x.dominant_group_informative.eq(~invalid).all())
ck('point_latest_group_requires_informative',p.agri_latest_crop_dominant_group.notna().eq(p.agri_latest_crop_dominant_group_informative.fillna(False)).all())
latestgroups=p[['agri_municipality_code','agri_latest_crop_dominant_group']].merge(m[['municipality_code','latest_crop_dominant_group']],left_on='agri_municipality_code',right_on='municipality_code',how='left',validate='many_to_one')
ck('point_latest_group_matches_municipal',latestgroups.agri_latest_crop_dominant_group.fillna('__NULL__').eq(latestgroups.latest_crop_dominant_group.fillna('__NULL__')).all())
audit={'status':'PASS' if all(c['pass'] for c in checks) else 'FAIL','checks_passed':sum(c['pass'] for c in checks),'checks_total':len(checks),'independence':'module_author_readback_not_external_review','evidence_status_counts':statuses,'checks':checks}
(R/'READBACK_VERIFICATION.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');assert audit['status']=='PASS';print(audit['status'],audit['checks_passed'],'/',audit['checks_total'])
