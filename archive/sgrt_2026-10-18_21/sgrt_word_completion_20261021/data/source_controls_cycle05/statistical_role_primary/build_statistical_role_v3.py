#!/usr/bin/env python3
"""Correct semantic distinction: NP name subtype is not statistical urban/rural category."""
from pathlib import Path
import pandas as pd,json,hashlib
H=Path(__file__).resolve().parent;S=H.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=S/'source_settlement_role_tristate_primary2021_cycle05.parquet';d=pd.read_parquet(p);before=sha(p)
mask=d.source2021_type_code_conflict&d.primary202101_exact_code_and_normalized_name&d.source2021_native_code_role.eq('rural')
assert mask.sum()==62
# Actual primary NP roster code, not unchecked secondary code: normative NP101–999 is rural.
# NAME1 preserves a regional legal/formal subtype; it does not supersede statistical category.
d['source2021_subtype_statistical_category_disagreement']=mask
d['source2021_settlement_subtype']=d.source2021_role_original_type
for c,v in [('source2021_rural_role',True),('source2021_urban_role',False)]:d.loc[mask,c]=v
d.loc[mask,'source2021_effective_settlement_type']=d.loc[mask,'source2021_role_original_type']
d.loc[mask,'source2021_role_evidence']='actual_primary_Jan2021_exact_NPcode_and_name_rural101plus_statistical_category_NAME1_subtype_preserved'
crimea=mask&d.source2021_role_region.eq('крым');assert crimea.sum()==56
d['source2021_additional_Crimea_law18_article5_rural_proof']=crimea
law=H/'crimea_law18_2014_replica.pdf';text=(H/'crimea_law18_2014_replica.pdf.txt').read_text();assert '3. К сельским населенным пунктам' in text and 'поселок городского типа;' in text
# Explicitly expose whether the concrete primary record code/name was corroborated.
d['source2021_role_semantic_note']='Statistical urban/rural role is separate from regional settlement subtype; пгт/рп/кп names may be statistically rural.'
out=H/'source_settlement_statistical_role_primary2021_v3.parquet';d.to_parquet(out,index=False)
d[mask].to_csv(H/'62_statistical_rural_named_pgt_rp_kp.csv',index=False)
u=d[d.source2021_population_additive_role&d.source2021_rural_role.isna()&d.source2021_role_population_2021.gt(0)];u.to_csv(H/'remaining_unknown_positive_statistical_role.csv',index=False)
checks=[('actual62primarycode_name_suffix101plus_rural',d.loc[mask,'source2021_rural_role'].eq(True).all() and d.loc[mask,'source2021_urban_role'].eq(False).all()),('Crimea56primarylaw_category_proof',int(crimea.sum())==56),('one_positive_unknown_resident_preserved',len(u)==1 and u.source2021_role_population_2021.sum()==1),('immutable_v2_preserved',sha(p)==before)]
rec=dict(status='STATISTICAL_ROLE_V3_CORRECTS_NAME_SUBTYPE_CATEGORY_CONFLATION',supersedes_semantics_of='source_settlement_role_tristate_primary2021_cycle05.parquet; frozen v2 retains raw concordance but its62 urban overrides are WRONG and must not be used',checks=[dict(check=k,passed=bool(v)) for k,v in checks],n_failed=sum(not v for k,v in checks),role_counts={str(k):int(v) for k,v in d.source2021_rural_role.value_counts(dropna=False).items()},rural62_population2021=int(d.loc[mask,'source2021_role_population_2021'].sum()),Crimea56population2021=int(d.loc[crimea,'source2021_role_population_2021'].sum()),unknown_positive_population2021=int(u.source2021_role_population_2021.sum()),actual_primary_normative_source='administration2021_cycle05/sources/VvedOKTMO.docx paragraphs111–115; actual 2021-01-18 CSV exact NP code/name concordance62rows',Crimea_legal_proof=dict(path=str(law),sha256=sha(law),article='Article5 PDFpages2–3',host='roscadastre.ru legal PDF replica; actualRosstat2021methodologyURL acquisition failed503, indexed snippet not substituted for bytes'),outputs={q.name:dict(sha256=sha(q),bytes=q.stat().st_size) for q in [out,H/'62_statistical_rural_named_pgt_rp_kp.csv',H/'remaining_unknown_positive_statistical_role.csv',Path(__file__)]})
(H/'statistical_role_v3_receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rec,ensure_ascii=False,indent=2))
