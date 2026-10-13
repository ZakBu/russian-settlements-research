"""Independent accepted State API replay of the separate status-history delta."""
import json,sys,importlib.util
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];E=ROOT/'research_rebuild/evidence';OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
spec=importlib.util.spec_from_file_location('native_verify_finite',E/'working_full_chain_20261007/replay_additional_native_20261008.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
def main():
    receipt=json.loads((OUT/'separate_native_application_receipt.json').read_text())
    assert sha(OUT/'native_typechange.py')==receipt['code_sha256']
    for p,h in receipt['input_pins'].items():assert sha(Path(p))==h,p
    for p,h in receipt['output_pins'].items():assert sha(OUT/p)==h,p
    s=load(51);assert helper.finite(s)==receipt['before_finite'] and s.metrics()==receipt['before']
    fields=['source_record_id','population','population_value_quality','settlement_name','settlement_type','source_file','source_sha256','source_locator']
    before=s.obs[fields].copy();oldpoints={sid:dict(row) for sid,row in s.point_rows.items()}
    s.add_deltas([OUT/'accepted_separate_native_identity_edge_delta.csv'],[OUT/'accepted_separate_native_point_use_delta.csv'])
    assert helper.finite(s)==receipt['after_finite'] and s.metrics()==receipt['after'] and before.equals(s.obs[fields])
    for sid,row in oldpoints.items():assert s.point_rows[sid]==row
    current='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:26777'
    point=s.point_rows[current];assert s.by_id.loc[current,'oktmo']=='27734000106' and s.by_id.loc[current,'okato']=='27420000001'
    for row in pd.read_csv(OUT/'accepted_separate_native_point_use_delta.csv').itertuples():
        assert row.coordinate_source_record_id==current and row.latitude==point['latitude'] and row.longitude==point['longitude']
    result=dict(status='passed_independent_actual51_State_API_native_status_history_replay',
        application_receipt_sha256=sha(OUT/'separate_native_application_receipt.json'),population_metadata_quality_unchanged=True,
        every_existing_admitted_point_preserved=True,explicit_status_change_not_direct_absorption=True,
        after_finite=helper.finite(s),finite_native_gain=receipt['finite_native_gain'],code_sha256=sha(Path(__file__)))
    (OUT/'separate_native_verification_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
