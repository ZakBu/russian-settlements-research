"""Execute the reviewed1910 overlay only after the actual canonical64 export."""
from pathlib import Path
import json,subprocess,sys,hashlib
Z=Path(__file__).resolve().parent;E=Z.parent;R=E.parents[1];D=Path('/workspace/settlements-delivery/working-full-chain-20261007')
export=json.loads((E/'working_full_chain_20261007/export_receipt.json').read_text());assert export['working_stage']==64
C=E/'main_axis_residual_application64_20261008';cr=json.loads((C/'application_receipt.json').read_text());assert cr['intended_working_stage']==64 and cr['canonical_State_API_replay_passed']
args=[sys.executable,str(Z/'apply_cumulative_primary_overlay.py'),'--stage','64','--main',export['file'],'--expected-main-sha256',export['sha256'],'--primary-credit-roster',str(C/'applied_primary_credited_UID_roster.csv.gz'),'--expected-credit-sha256',cr['output_pins']['applied_primary_credited_UID_roster.csv.gz']['sha256'],'--composer-receipt',str(C/'application_receipt.json'),'--current-observations',str(C/'applied_state_observations.parquet'),'--expected-current-observations-sha256',cr['output_pins']['applied_state_observations.parquet']['sha256'],'--delivery-output-dir',str(D),'--retain-existing-as-stage','63','--expected-existing-effective-sha256','74feb8b46eca34a6afed35cfb37d18863d60ee3d11234226ec3392c7f0e25612']
prior=json.loads((E/'next_overlay_application_20261008/application_receipt.json').read_text())['claim_input_pins']
prior[str(E/'residual_source_followup_20261008/accepted_county_bound_primary2010_addon_8.csv.gz')]='e381587945a8fb8bf913233f351d13c1682fbe6630cfd84d775e31f88f5029d2'
prior[str(E/'residual_source_followup_20261008/accepted_all_regions_county_bound_primary2010_addon_127.csv.gz')]='0f17caea9cc1191f70d2944b22ea4a657215822d14d312b31b49e8daca487f72'
for path,sh in prior.items():args.extend(['--claim-file',path,'--expected-claim-sha256',sh])
with (Z/'execution.log').open('w') as log:subprocess.run(args,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Applied1910claims after canonical64; see application_receipt.json')
