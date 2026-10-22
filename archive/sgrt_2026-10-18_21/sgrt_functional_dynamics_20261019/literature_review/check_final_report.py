"""Check final report's quantitative readout against accepted result summaries."""
from pathlib import Path
import json,hashlib
import pandas as pd
import pyarrow.parquet as pq

R=Path(__file__).resolve().parents[1]
O=Path(__file__).parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    report=R/'RESULTS.md';before=sha(report)
    text=report.read_text()
    checks=[]
    def ck(name,value):checks.append({'check':name,'pass':bool(value)})
    cal=R/'economy/pinned_calendar';w=R/'statistics/wave2'
    d=pd.read_csv(cal/'coverage_2011_2025.csv').set_index('year')
    ck('15calendar_years',list(d.index)==list(range(2011,2026)))
    ck('raw_rows63308662',d.source_rows.sum()==63308662)
    ck('point_year_rows2138550',pq.ParquetFile(cal/'point_exact_code_witnesses_2011_2025.parquet').metadata.num_rows==2138550==142570*15)
    expected={2011:[13150,3782,2004],2016:[14968,4717,2543],2021:[15321,5392,2942],2025:[12097,4320,2436]}
    cols=['points_with_direct_service_witness','points_with_ge2_direct_groups','points_with_ge3_direct_groups']
    for y,vals in expected.items():ck(f'annual_table_{y}',d.loc[y,cols].tolist()==vals)
    ck('2014_discontinuity_retained',[d.loc[y,cols[0]] for y in [2013,2014,2015]]==[14369,17286,15258])
    tr=pd.read_csv(cal/'trajectory_summary.csv').set_index('witness_trajectory').n_settlements.to_dict()
    want={'witness_all_years_unchanged_profile':2253,'witness_all_years_changed_profile':4029,'first_appearance_without_later_dropout':3524,'last_disappearance_without_return':5725,'one_internal_witness_episode':3785,'intermittent_witness_evidence':3989,'no_accepted_service_witness_any_year':119265}
    ck('all7trajectory_counts',tr==want and sum(tr.values())==142570)
    aa=json.loads((R/'economy/address_audit_2021_2025/ADDRESS_AUDIT.json').read_text())
    wa=json.loads((w/'ADDRESS_AUDIT.json').read_text())
    for k,v in {'common_INN':2331154,'common_reported_code_changed_valid_both':362312,'changed_code_stable_reported_coordinates':117852,'lost_native_link_stable_reported_coordinates':77646}.items():
        ck('address_'+k,aa['summary'][k]==wa['summary'][k]==v)
    s=aa['summary']
    ck('aliases_separate_sensitivity_counts',s['accepted_multi_INN_conditional_aliases']==1114 and s['additional_legal_records_from_conditional_aliases']==74244 and s['native_points_with_service_2025']==12097 and s['conditional_alias_points_with_service_2025']==12876)
    ck('aliases_not_official_crosswalk',s['alias_is_not_official_historical_crosswalk'] and not wa['conditional_alias_model_independently_retrained'])
    lc=wa['lifecycle']
    ck('lifecycle_partition',lc['only_INN_2021']==1081314 and lc['only2021_dissolution_known_after2021_le2025']==680192 and lc['only2021_dissolution_within_2021']==396971 and lc['only2021_dissolution_unknown']==4151 and 680192+396971+4151==1081314)
    accept=json.loads((w/'ACCEPTANCE.json').read_text())
    ck('wave2_4770_scope',accept['checks_total']==4770 and accept['all_4770_checks_pass'] and not accept['national_physical_service_or_sgrt_dynamics_established'])
    ck('wave2_audit_hashes_still_match',all(sha(w/a['file'])==a['sha256'] for a in accept['audits']))
    ck('bibliography_seminar_corrected','НИУ ВШЭ, 19.04.2025' in text and 'И к селу, и к городу: меняет ли появление маркетплейсов модели сельского образа жизни?' in text)
    ck('bibliography_Pokshishevskiy_subtitle','Население и география: теоретические очерки' in text)
    ck('report_independent_scope_exclusions_present','не переобучались независимым статистиком' in text and 'не распространяются на дополнительный слой 21 секции' in text)
    ck('report_4151_unknown_visible','4 151 ИНН дата ликвидации не установлена' in text)
    ck('report_unchanged_during_review',before==sha(report))
    remaining=[{'severity':'limitation_not_blocker','issue':'Conditional code aliases were not independently retrained or established as an official historical crosswalk; coordinates may be stale. Report keeps this sensitivity separate.'},{'severity':'limitation_not_blocker','issue':'All21 sector extension has author checks but is outside the ten-group independent calendar audit; report explicitly says so.'},{'severity':'limitation_not_blocker','issue':'Early2011–2013 code dates, national physical service history, real flows and complete SGRT boundaries remain unestablished; report preserves these limits.'}]
    out={'status':'ACCEPTED_WITH_EXPLICIT_SCOPE_LIMITS' if all(z['pass'] for z in checks) else 'NEEDS_CORRECTION','report_sha256':before,'report_file':'RESULTS.md','checks_total':len(checks),'checks_passed':sum(z['pass'] for z in checks),'checks':checks,'remaining_objections':remaining,'bibliographic_corrections_applied':['HSEseminar19April2025 distinguished from MGUauthor affiliation','Pokshishevskiy subtitle added'],'scope':'Final full-text construct/readout review against outputs and accepted independent wave2 summaries; this script does not rescan63million raw rows or independently retrain aliases. Earlier independent source/graph audits are separate.','evidence_sha256':{str(p.relative_to(R)):sha(p) for p in [R/'BIBLIOGRAPHY.csv',cal/'coverage_2011_2025.csv',cal/'trajectory_summary.csv',R/'economy/address_audit_2021_2025/ADDRESS_AUDIT.json',w/'ADDRESS_AUDIT.json',w/'ACCEPTANCE.json',w/'VERDICT.md']},'alias_external_check':{'Kosulino65706000291_to65506000139':{'official_exact_pair_verified':False,'status':'conditional_sensitivity_only','secondary_pointer_not_confirmation':'https://classinform.ru/oktmo/65506000000.html'},'Tarnogsky19642442101_to19542000101':{'official_exact_pair_verified':False,'status':'conditional_sensitivity_only','official_partial_context_url':'https://www.nalog.gov.ru/rn35/taxation/submission_statements/rekvizit/12986966/','official_partial_context':'FNSpublication29December2022 confirms new Tarnogsky municipal district-type code19542000 effective1January2023; not settlement11digit crosswalk.','equal_historical_boundaries_asserted':False,'unverified_boundary_change_lead':'Secondary sources cite Vologda decree475of11April2022 merging3villages into TarnogskyGorodok; original act not read, no finding asserted.'}}}
    (O/'FINAL_REPORT_REVIEW.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:out[k] for k in ['status','report_sha256','checks_total','checks_passed']},ensure_ascii=False))
    assert out['status']=='ACCEPTED_WITH_EXPLICIT_SCOPE_LIMITS'
if __name__=='__main__':main()
