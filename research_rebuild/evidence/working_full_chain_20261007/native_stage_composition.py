"""Root measured sequential native composition; original receipt gains are not summed."""
from pathlib import Path
import json, hashlib, subprocess


def load(out,stage,pin):
    final_stage=max(46,stage)
    path=out/f'native_composition_stages40_{final_stage}_receipt.json'
    pin(path);receipt=json.loads(path.read_text())
    assert receipt['status']==f'actual_sequential39_to{final_stage}_State_replay_passed'
    assert receipt['population_source_values_and_quality_unchanged']
    assert [entry['stage'] for entry in receipt['stages']]==list(range(40,final_stage+1))
    prior=None;baseline_references=[]
    for entry in receipt['stages']:
        source=Path(entry['source_application'])
        assert pin(source)==entry['source_application_sha256']
        for raw,claimed in entry['verified_input_and_ledger_pins'].items():
            path=Path(raw)
            # Original report-output pins are historical baseline references.
            historical_loader=path in {out.parents[2]/'research_rebuild/mass_linkage/working_state_20261007.py',out.parents[2]/'research_rebuild/mass_linkage/current_chain_state_20261007.py'}
            if out not in path.parents and not historical_loader: assert pin(path)==claimed
            else:
                historical=entry.get('historical_derived_output_verifications',{}).get(str(path),{})
                if 'verified_exact_frozen_snapshot' in historical:
                    assert path.name in {'replay_additional_native_20261008.py','working_state_20261007.py'}
                    assert historical['historical_calculation_code_only_not_new_build_input'] and historical['sha256']==claimed
                    snapshot=Path(historical['verified_exact_frozen_snapshot'])
                    if path.name=='working_state_20261007.py':
                        assert historical_loader
                        if claimed=='bc8477525df2519afeb5a57813e5ac68e27fe154cd354c3f93835d20759a56bd': assert snapshot==out.parent/'shared_rural_modern_point_corroboration_20261008'/'frozen_calculation_source_stage60.py'
                        else:
                            assert snapshot==out.parent/'combined_inherited_ownpoint_application_20261008'/'frozen_calculation_source_stage59.py'
                            assert claimed=='2d8a098ba81a7c3227c968fb97ebd034a31e1a126fc4e01f88d04c2b8f5a466a'
                    else: assert snapshot==out.parent/'accepted_lifecycle_ownpoint_application_20261008'/'frozen_calculation_source_stage47.py'
                    assert pin(snapshot)==claimed
                    baseline_references.append({'path':str(path),'sha256':claimed,'verified_exact_frozen_snapshot':str(snapshot),'verification':'exact_frozen_calculation_source_not_live_build_input'})
                    continue
                assert historical_loader or path.name in {'build_report.py','secondary_full3.py','native_stage_composition.py','replay_additional_native_20261008.py','export_full3.py','verify_export.py','direct_inclusion_paths.py','qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','complete_publisher_partition_members.csv','qualified_physical_observations.csv','formation_path_native_credit_union.csv','direct_inclusion_transformation_path_native_credit_union.csv','coverage_receipt.json'}
                relative=str(path.relative_to(out.parents[2]))
                matching_commits=[]
                for baseline_commit in ['dba51d5','f67ea9111a2d7932ef7e55a7015a120ac3a50caa','0b8c3b0bda66b4dcec86ef9ff1ce706dc8fdcac7','65e88651f238173693e14c9654888b36b2fc9d44','fce754a35ddd2a182b242d6d415797e177860532']:
                    original=subprocess.run(['git','show',baseline_commit+':'+relative],cwd=out.parents[2],capture_output=True)
                    if original.returncode==0 and hashlib.sha256(original.stdout).hexdigest()==claimed: matching_commits.append(baseline_commit)
                assert matching_commits,('Historical report input does not match verified baseline Git blobs',str(path),claimed)
                baseline_commit=matching_commits[0]
                baseline_references.append({'path':str(path),'sha256':claimed,'verification':f'exact_baseline_Git_blob_{baseline_commit}_historical_derived_output_not_live_build_input'})
        before=entry['before_finite_all3_all_points'];after=entry['after_finite_all3_all_points']
        if prior is not None: assert before==prior
        assert after['histories']-before['histories']==entry['actual_net_histories']
        for year,pop in after['populations_by_year'].items():
            assert pop-before['populations_by_year'][year]==entry['actual_net_population_by_year'][year]
        prior=after
    assert prior==receipt['final']
    assert receipt['stages'][46-40]['after_finite_all3_all_points']=={'histories':138836,'populations_by_year':{'2002':126709814,'2010':123868391,'2021':124470404}}
    receipt['historical_baseline_output_verification']=baseline_references
    assert 40<=stage<=final_stage
    return receipt['stages'][stage-40]['after_finite_all3_all_points'],receipt
