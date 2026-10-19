"""Supervisor direct checks of typed historical links and external-case inference."""
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
O=Path(__file__).resolve().parent;R=O.parent;repo=R.parent.parent;checks=[]
def ck(n,v,**kw):
 checks.append(dict(test=n,passed=bool(v),**kw))
 if not v:raise AssertionError(checks[-1])
raw=pd.read_parquet(repo/'research_rebuild/evidence/historical_sources_integration_20261014/population_1989_selected_long.parquet');co=pd.read_parquet(R/'data/cohort1989.parquet');p=pd.read_parquet(R/'data/panel.parquet');source=pd.read_csv(repo/'publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz',usecols=['entity_uid','source_record_id_2002','source_record_id_2010','source_record_id_2021'])
ck('raw_history_root_unique',raw.root.is_unique);ck('cohort1989_one_row_per_modern_object',co.id.is_unique);ri=raw.set_index('root');j=co.set_index('root').join(ri[['population','source_kind','population_basis','historical_boundary_comparability']],rsuffix='_raw',validate='one_to_one');ck('all_historical_values_unmodified',np.array_equal(j.population,j.population_raw));ck('all_historical_bases_retained',j.population_basis.fillna('MISSING').eq(j.population_basis_raw.fillna('MISSING')).all());ck('all_historical_boundary_flags_retained',j.historical_boundary_comparability.fillna('MISSING').eq(j.historical_boundary_comparability_raw.fillna('MISSING')).all())
# Independently build source-key to modern-ID incidence (not a fuzzy/spatial match).
lookup={}
for year in [2002,2010,2021]:
 for sid,key in zip(source.entity_uid,source[f'source_record_id_{year}']):
  if isinstance(key,str):lookup.setdefault(key,set()).add(sid)
links={};modern_occurrence={}
for _,row in raw.iterrows():
 candidates=lookup.get(row.root,set())|lookup.get(row.anchor_source_record_id,set())
 links[row.root]=candidates
 for sid in candidates:modern_occurrence.setdefault(sid,set()).add(row.root)
accepted={root:next(iter(ids)) for root,ids in links.items() if len(ids)==1 and len(modern_occurrence[next(iter(ids))])==1};ck('all_1989_exact_unique_links_independently_reconstructed',accepted==dict(zip(co.root,co.id)),accepted=len(accepted),raw=len(raw));pi=p.set_index('id');ck('panel_historical_values_match_accepted_only',np.array_equal(pi.loc[co.id,'population_1989'],co.population) and pi.population_1989.notna().sum()==len(co));ck('primary_1989_status_exact_source_kind',co.is_primary_source_kind.eq(co.source_kind.isin(['official_census_transcription','primary_regional_census'])).all());ck('historical_partial_coverage_not_full',len(co)<len(p));ck('historical_types_not_falsely_homogeneous',co.population_basis.nunique()>1 and co.historical_boundary_comparability.eq('UNKNOWN').any())
# Case correspondence checks independently of validator code; source rereading belongs to link_validator.
V=R/'validation';cases=pd.read_csv(V/'cases_sources.csv');summary=json.loads((V/'case_summary.json').read_text());m=pd.read_parquet(R/'model/nearest_membership.parquet').set_index('id');c=pd.read_parquet(R/'model/centers.parquet').set_index('id');rows=[]
for _,row in cases.iterrows():
 assigned=m.loc[row.origin_id,'center_id'];direct=assigned==row.expected_center_id;chain=c.loc[assigned,'chain_ids'].split('|') if assigned in c.index else []
 rows.append(dict(case_id=row.case_id,direct=direct,chain=row.expected_center_id in chain,assigned_id=assigned,expected_center_id=row.expected_center_id))
z=pd.DataFrame(rows);ck('case_count_region_URL_actual',len(cases)==13 and cases.region.nunique()==10 and cases.source_url.nunique()==10);ck('case_direct_and_chain_counts_recomputed',int(z.direct.sum())==summary['nearest_direct_match'] and int(z.chain.sum())==summary['nearest_chain_match'],direct=int(z.direct.sum()),chain=int(z.chain.sum()));ck('qualified_case_exclusion_recomputed',int(z[z.case_id.ne('C05')].chain.sum())==summary['without_qualified_C05_nearest_chain_match']);ck('casebook_claims_no_direct_OD_flows',not cases.direct_flow.any() and summary['direct_observed_OD_cases']==0);ck('casebook_not_synchronous_2010',not cases.synchronous_2010_evidence.any() and summary['synchronous2010_cases']==0)
# On paired administrative rows the same denominator is required; review checked artifacts.
audit=json.loads((V/'validation_audit.json').read_text());result=dict(status='PASS',passed=len(checks),failed=0,checks=checks,historical_coverage=dict(raw_rows=len(raw),matched_ordinary_objects=len(co),primary_source_kind=int(co.is_primary_source_kind.sum()),basis_counts=co.population_basis.fillna('MISSING').value_counts().to_dict(),boundary_counts=co.historical_boundary_comparability.fillna('MISSING').value_counts().to_dict()),external_cases=dict(n_cases=len(cases),n_URL=cases.source_url.nunique(),direct=int(z.direct.sum()),chain=int(z.chain.sum()),direct_flow_pairs=0,review='case inference independently recomputed; fresh webpage retrieval performed by separate link_validator, not this script'));z.to_csv(O/'independently_recomputed_external_cases.csv',index=False);tmp=O/'history_validation_checks.json.tmp';tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2));json.loads(tmp.read_text());tmp.replace(O/'history_validation_checks.json');print(json.dumps(result,ensure_ascii=False,indent=2))
