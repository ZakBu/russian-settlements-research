#!/usr/bin/env python3
"""Independently read dated official NP rows; explicit primary type outranks suffix.
2021-01 snapshot precedes October census: no unproved January/October identity bridge.
"""
from pathlib import Path
import pandas as pd,numpy as np,re,json,hashlib
H=Path(__file__).resolve().parent; R=H.parents[1]; P=R/'administration2021_cycle05/sources/data-20210118-structure-20150128.csv'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return re.sub(r'[^\w]+','',str(s).casefold().replace('ё','е'))
d=pd.read_csv(P,sep=';',encoding='cp1251',header=None,dtype=str,keep_default_na=False);d['primary_csv_row_1based']=np.arange(len(d))+1;d['official_code']=d[0]+d[1]+d[2]+d[3];d=d[d[5].eq('2')&d[3].ne('000')].copy();assert d.official_code.is_unique
prefix={'г':False,'пгт':False,'рп':False,'кп':False,'дп':False,'гп':False,'д':True,'с':True,'х':True,'ст-ца':True,'аул':True,'аал':True,'у':True,'починок':True,'сл':True,'погост':True,'арбан':True,'выселок':True,'заимка':True,'кордон':True}
d['official_prefix']=d[6].str.split().str[0];d['official_basename']=d[6].str.split(n=1).str[1];d['official_explicit_rural_role']=d.official_prefix.map(prefix);d['official_norm_name']=d.official_basename.map(norm)
a=pd.read_parquet(H/'source_settlement_role_tristate_cycle05.parquet');m=a.merge(d[['official_code',6,'official_prefix','official_basename','official_explicit_rural_role','official_norm_name','primary_csv_row_1based',11,12]],left_on='source2021_native_NP_oktmo11',right_on='official_code',how='left',validate='many_to_one');m=m.rename(columns={6:'primary202101_official_name',11:'primary202101_approval_date',12:'primary202101_effective_date'})
m['primary202101_exact_code_and_normalized_name']=m.official_code.notna()&m.source2021_role_original_name.map(norm).eq(m.official_norm_name)
m['primary202101_explicit_type_suffix_exception']=m.primary202101_exact_code_and_normalized_name&m.official_explicit_rural_role.notna()&m.source2021_native_code_role.notna()&(m.official_explicit_rural_role.ne(m.source2021_native_code_role.eq('rural')))
# Strict alternate NP-code witness: same eight-digit native municipality, exact normalized
# name, explicit primary type, unique official sibling. No spatial/fuzzy/name-only bridge.
alternates=[]
for i,z in m[m.source2021_role_has_dated_source & ~m.primary202101_exact_code_and_normalized_name & m.source_latest_explicit_type_role.isna() & m.source2021_native_code_role.str.startswith('urban',na=False) & ~m.source2021_role_evidence.str.startswith('primary_law')].iterrows():
 cand=d[d.official_code.str[:8].eq(str(z.source2021_native_NP_oktmo11)[:8]) & d.official_norm_name.eq(norm(z.source2021_role_original_name)) & (d.official_explicit_rural_role.notna() | (d.official_prefix.eq('п') & d.official_code.str[-3:].astype(int).ge(101)))]
 if len(cand)==1:
  v=cand.iloc[0];vr=bool(v.official_explicit_rural_role) if pd.notna(v.official_explicit_rural_role) else True;alternates.append(dict(id=z.id,source_native_code=z.source2021_native_NP_oktmo11,primary_official_code=v.official_code,primary_official_name=v[6],primary_csv_row_1based=int(v.primary_csv_row_1based),proof='same_native8municipality_and_exact_normalized_NPname_unique_typed_primary_sibling',primary_rural_role=vr))
alt=pd.DataFrame(alternates);alt.to_csv(H/'primary2021_strict_same_municipality_nativecode_witness.csv',index=False)
m['source2021_role_before_primary_check']=m.source2021_rural_role
# Never override independently adopted law or non-additive context.
use=m.primary202101_exact_code_and_normalized_name&m.official_explicit_rural_role.notna()&m.source2021_population_additive_role&m.source2021_role_has_dated_source&~m.source2021_role_evidence.str.startswith('primary_law')
m.loc[use,'source2021_rural_role']=pd.array(m.loc[use,'official_explicit_rural_role'],dtype='boolean');m.loc[use,'source2021_urban_role']=~m.loc[use,'source2021_rural_role'];m.loc[use,'source2021_effective_settlement_type']=np.where(m.loc[use,'official_explicit_rural_role'].astype(bool),m.loc[use,'source2021_role_original_type'],np.where(m.loc[use,'official_prefix'].eq('г'),'город','пгт'));m.loc[use,'source2021_role_evidence']='primary_official_Jan2021_exact_NPcode_and_name_explicit_type'
for v in alternates:
 k=m.id.eq(v['id']);m.loc[k,'source2021_rural_role']=v['primary_rural_role'];m.loc[k,'source2021_urban_role']=not v['primary_rural_role'];m.loc[k,'source2021_effective_settlement_type']='посёлок' if v['primary_rural_role'] else 'пгт';m.loc[k,'source2021_role_evidence']='primary_Jan2021_unique_exact_NPname_within_same_native8municipality_code_anomaly_witness'
# A primary mismatch remains visible; no substitution of native codes or fuzzy names.
m['primary202101_source_sha256']=sha(P);m['primary202101_to_census_Oct2021_status_continuity_unproven']=True
for c in ['source2021_rural_role','source2021_urban_role','source_latest_type_rural_role']:m[c]=pd.array(m[c],dtype='boolean')
m.to_parquet(H/'source_settlement_role_tristate_primary2021_cycle05.parquet',index=False)
m[m.primary202101_explicit_type_suffix_exception].to_csv(H/'primary2021_explicit_type_suffix_exceptions.csv',index=False)
c=m[m.source2021_type_code_conflict].copy();c.to_csv(H/'primary2021_original63_conflict_resolution.csv',index=False)
u=m[m.source2021_population_additive_role&m.source2021_rural_role.isna()&m.source2021_role_population_2021.gt(0)];u.to_csv(H/'primary2021_unresolved_positive_role.csv',index=False)
# Missing exact code in the January roster is a dated source alignment audit, not evidence of absence in October.
m[m.source2021_role_has_dated_source&~m.primary202101_exact_code_and_normalized_name].to_parquet(H/'primary2021_code_name_alignment_queue.parquet',index=False)
checks=[('same173862uniqueaxisIDs_order',m.id.equals(a.id) and m.id.is_unique),('primary155627NProws_unique',len(d)==155627 and d.official_code.is_unique),('62of63strongconflicts_primarytyped_exact_code_name',int((c.primary202101_exact_code_and_normalized_name&c.official_explicit_rural_role.notna()).sum())==62),('62resolved_as_primary_explicit_urban',c.loc[c.primary202101_exact_code_and_normalized_name,'source2021_rural_role'].eq(False).all()),('remaining1person_not_fabricated',len(u)==1 and u.source2021_role_population_2021.sum()==1),('nohistoricalonly2021role_backcast',m.loc[~m.source2021_role_has_dated_source,'source2021_rural_role'].isna().all()),('nonadditive_roles_unknown',m.loc[~m.source2021_population_additive_role,'source2021_rural_role'].isna().all())]
names=['primary2021_strict_same_municipality_nativecode_witness.csv','resolve_primary2021_role_exceptions.py','source_settlement_role_tristate_primary2021_cycle05.parquet','primary2021_explicit_type_suffix_exceptions.csv','primary2021_original63_conflict_resolution.csv','primary2021_unresolved_positive_role.csv','primary2021_code_name_alignment_queue.parquet']
rec=dict(status='PRIMARY_DATED_EXPLICIT_TYPES_OVERRIDE_NORMATIVE_SUFFIX_EXCEPTIONS',checks=[dict(check=k,passed=bool(v)) for k,v in checks],n_failed=sum(not v for k,v in checks),primary_source=dict(path=str(P),sha256=sha(P),native_NP_rows=len(d),period='2021-01-18; dates of entry <=2021-01-01'),exact_code_name_np_matches=int(m.primary202101_exact_code_and_normalized_name.sum()),primary_explicit_type_admitted=int(use.sum()),normative_suffix_exceptions=int(m.primary202101_explicit_type_suffix_exception.sum()),original63_resolved=62,remaining_positive_unknown_NP=len(u),remaining_positive_unknown_population=int(u.source2021_role_population_2021.sum()),role_counts={str(k):int(v) for k,v in m.source2021_rural_role.value_counts(dropna=False).items()},temporal_caveat='January classifier precedes October census; code/name concordance proves record identity, not absence of intervening status change. No arbitrary ID/code replacements.',outputs={n:dict(sha256=sha(H/n),bytes=(H/n).stat().st_size) for n in names});(H/'primary2021_role_resolution_receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in rec.items() if k!='outputs'},ensure_ascii=False,indent=2))
