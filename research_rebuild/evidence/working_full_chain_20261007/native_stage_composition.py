"""Root measured sequential native composition; original receipt gains are not summed."""
from pathlib import Path
import json, hashlib, subprocess


def load(out,stage,pin):
    path=out/'native_composition_stages40_46_receipt.json'
    pin(path);receipt=json.loads(path.read_text())
    assert receipt['status']=='actual_sequential39_to46_State_replay_passed'
    assert receipt['population_source_values_and_quality_unchanged']
    assert [entry['stage'] for entry in receipt['stages']]==list(range(40,47))
    prior=None;baseline_references=[]
    for entry in receipt['stages']:
        source=Path(entry['source_application'])
        assert pin(source)==entry['source_application_sha256']
        for raw,claimed in entry['verified_input_and_ledger_pins'].items():
            path=Path(raw)
            # Original report-output pins are historical baseline references.
            if out not in path.parents: assert pin(path)==claimed
            else:
                assert path.name in {'qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','complete_publisher_partition_members.csv','qualified_physical_observations.csv'}
                relative=str(path.relative_to(out.parents[2]))
                original=subprocess.run(['git','show','dba51d5:'+relative],cwd=out.parents[2],check=True,capture_output=True).stdout
                assert hashlib.sha256(original).hexdigest()==claimed
                baseline_references.append({'path':str(path),'sha256':claimed,'verification':'exact_stage39_Git_blob_dba51d5_historical_derived_output_not_live_build_input'})
        before=entry['before_finite_all3_all_points'];after=entry['after_finite_all3_all_points']
        if prior is not None: assert before==prior
        assert after['histories']-before['histories']==entry['actual_net_histories']
        for year,pop in after['populations_by_year'].items():
            assert pop-before['populations_by_year'][year]==entry['actual_net_population_by_year'][year]
        prior=after
    assert prior==receipt['final']
    assert receipt['final']=={'histories':138836,'populations_by_year':{'2002':126709814,'2010':123868391,'2021':124470404}}
    receipt['historical_baseline_output_verification']=baseline_references
    if stage<=46: return receipt['stages'][stage-40]['after_finite_all3_all_points'],receipt
    raise AssertionError('Final native stage requires explicit root composition admission')
