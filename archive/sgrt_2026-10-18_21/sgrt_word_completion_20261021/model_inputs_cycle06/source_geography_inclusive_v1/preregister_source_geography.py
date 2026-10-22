#!/usr/bin/env python3
"""Source-only seventh paired design; no model predictions, Mi, routes or metrics read."""
from pathlib import Path
import json,hashlib,datetime,re,itertools
import pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parents[1];REPO=ROOT.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.relative_to(REPO))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def run():
 assert not (H/'preregistration.json').exists(),'Do not overwrite preregistration'
 base=ROOT/'model_inputs_cycle06/config_baseline_provisional.json';c=json.loads(base.read_text());source=ROOT/'model_inputs_cycle05/relinked_v4';admission=ROOT/'reviews/cycle05/relinked_v4_independent/audit.json';assert json.loads(admission.read_text())['all_checks_passed'] is True
 data={};pins={rel(p):sha(p) for p in [base,source/'source_freeze_manifest.json',admission]};controls=[];physical={};eligibility={};checks=[]
 for family,prefix in [('education','school_'),('commerce','services_'),('medical','medical_')]:
  fp=source/family/'settlement_features_full_axis.parquet';op=source/family/'source_objects_relinked.parquet';f=pd.read_parquet(fp);o=pd.read_parquet(op);canonical='count_canonical_site_id' if family=='medical' else 'canonical_site_id';modes=['baseline','conditional_additional','coordinate_candidate'] if family=='medical' else ['baseline','candidate_additional'];countcols=['count_'+v+'_uid' for v in modes]
  sets={mode:set(o.loc[o['count_'+mode+'_uid'].notna(),canonical]) for mode in modes}
  for a,b in itertools.combinations(modes,2):assert not sets[a]&sets[b],(family,a,b)
  allcounts=pd.concat([o.loc[o[q].notna(),[canonical,q]].rename(columns={q:'uid'}) for q in countcols]);assert allcounts.groupby(canonical).uid.nunique().le(1).all();checks.append(dict(family=family,canonical_channel_disjoint=True,single_global_counted_uid_per_site=True))
  data[family]=(f,o,canonical,modes,prefix);pins.update({rel(p):sha(p) for p in [fp,op]})
 for function,original in c['physical_features'].items():
  new=[]
  for fullcol in original:
   matches=[(fam,v) for fam,v in data.items() if fullcol.startswith(v[4]) and fullcol[len(v[4]):] in v[0]];assert len(matches)==1,(function,fullcol);family,(f,o,canonical,modes,prefix)=matches[0];col=fullcol[len(prefix):]
   if family=='education':group=re.fullmatch('education_osm2021_(.+)_baseline_count',col)[1];subset=o.education_group.eq(group)
   elif family=='commerce':group=re.fullmatch('services_osm2021_(.+)_baseline_count',col)[1];subset=o.service_group.eq(group)
   elif col=='medical_osm_baseline_general_and_dental_clinical_sites_count':subset=o.revised_broad_function.isin(['healthcare','dentistry'])
   elif col=='medical_osm_baseline_explicit_hospital_sites_count':subset=o.revised_broad_function.eq('healthcare')&(o.amenity.eq('hospital')|o.healthcare.eq('hospital'))
   else:raise ValueError('Undeclared primary medical format '+col)
   per=[]
   for mode in modes:
    feature=col.replace('_baseline_', '_'+mode+'_');assert feature in f,feature;uid='count_'+mode+'_uid';a=o.loc[subset&o[uid].notna(),[uid,canonical]].drop_duplicates();got=a.groupby(uid).size();expected=f.set_index('id')[feature];actual=expected.index.to_series().map(got).fillna(0).astype('int64');assert actual.equals(expected.astype('int64')),feature
    new.append(prefix+feature);per.append(expected);controls.append(dict(function=function,family=family,format=col,channel=mode,accepted_canonical_sites=int(expected.sum()),positive_NP=int(expected.gt(0).sum()),raw_canonical_readback_equal=True))
   union=sum(per);controls.append(dict(function=function,family=family,format=col,channel='disjoint_union',accepted_canonical_sites=int(union.sum()),positive_NP=int(union.gt(0).sum()),raw_canonical_readback_equal=True))
  physical[function]=new
  if function in c['center_eligibility_2021_features']:eligibility[function]=new
 assert 'services_services_osm2021_atm_baseline_count' not in sum(physical.values(),[])
 assert all('other_retail' not in v and 'market_' not in v for v in physical['trade']);assert all('_bank_' in v for v in physical['finance'])
 controls=pd.DataFrame(controls);controls.to_csv(H/'source_channel_counts_before_model.csv',index=False)
 protocol=dict(status='PREREGISTERED_SEVENTH_PAIRED_SOURCE_GEOGRAPHY_SENSITIVITY_BEFORE_OUTCOMES_NOT_EXECUTED',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),variant='source_geography_inclusive',paired_reference='baseline, same accepted final2021 transport_access_v2 once independently admitted',distinct_from='inclusive_candidates changes eligibility policy to broad catalogue; this seventh variant retains baseline eligibility criteria and only expands source linkage channels',changed=['physical source geography: strict baseline plus disjoint additional linkage channels','same expanded dated source columns for eligibility evidence under unchanged baseline criteria'],unchanged=['LARGE retail only','BANK without ATM','generalclinical+dental','general school','physicaladministration','five ownMi domains/formula','statisticalrural role policy','center eligibility policy thresholds/rules','Pmin.35','Huff decay/outside/budgets','Ci formula onepass','GMM selection','canonical Wordcriteria','nonmass contextual layers'],channels={'education':'baseline+candidate_additional coordinate linkage; no fabricated separate conditional channel','commerce':'baseline+candidate_additional coordinate linkage; no fabricated separate conditional channel','medical':'baseline+conditional_additional+coordinate_candidate; accepted V4 canonical precedence; nearest-coordinate ties quarantined'},canonical_policy='Each source canonical physical site is counted at one NP and in one channel; raw source readback independently recomputed before model. No medical class/format broadening. No cross-domain school/health merger assumed.',primary_unchanged=True,no_outcome_or_membership_or_Mi_read=True,no_external_label_training=True,expected_direction_not_preregistered=True,comparison_metrics_preregistered=['Mi/component differences','candidate IDs and empirical ranks','all-level membership and population-weighted assignment agreement with baseline','alllevel corrected configuration changes','all nine types statuses and named changed cases','Ci and roleunknown coverage','same fixed external52 and VPO/SPO diagnostic with original labels/strata; no retuning'],transport_binding='PENDING new transport_access_v2 graph/matrix independent admission; no route binding or model run in this task',physical_features=physical,center_eligibility_2021_features=eligibility,source_count_controls=rel(H/'source_channel_counts_before_model.csv'),source_count_controls_sha256=sha(H/'source_channel_counts_before_model.csv'),channel_checks=checks,source_sha256=pins,code_sha256=sha(Path(__file__)))
 dump(H/'preregistration.json',protocol);dump(H/'future_config_patch_NOT_BOUND.json',dict(cycle05_variant='source_geography_inclusive',physical_features=physical,center_eligibility_2021_features=eligibility,center_policy_inherited_byteexact_from_baseline=True,components_and_nonservice_settings_unchanged=True,provenance_sidecars=[rel(H/'preregistration.json'),rel(admission)],not_a_runnable_config=True))
 files=[p for p in H.iterdir() if p.is_file()];dump(H/'freeze_manifest.json',dict(status='FROZEN_SOURCE_ONLY_PREREGISTRATION_BEFORE_ANY_SEVENTH_MODEL_OUTPUT',files={p.name:sha(p) for p in files}));print(controls.to_string(index=False))
if __name__=='__main__':run()
