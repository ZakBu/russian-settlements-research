"""Execute the reviewed1961 overlay only after the actual canonical66 export."""
from pathlib import Path
import json,subprocess,sys,hashlib
Z=Path(__file__).resolve().parent;E=Z.parent;R=E.parents[1];D=Path('/workspace/settlements-delivery/working-full-chain-20261007')
export=json.loads((E/'working_full_chain_20261007/export_receipt.json').read_text());assert export['working_stage']==66
C=E/'main_axis_residual_application66_20261008';cr=json.loads((C/'application_receipt.json').read_text());assert cr['intended_working_stage']==66 and cr['canonical_State_API_replay_passed']
args=[sys.executable,str(Z/'apply_cumulative_primary_overlay.py'),'--stage','66','--main',export['file'],'--expected-main-sha256',export['sha256'],'--primary-credit-roster',str(C/'applied_primary_credited_UID_roster.csv.gz'),'--expected-credit-sha256',cr['output_pins']['applied_primary_credited_UID_roster.csv.gz']['sha256'],'--composer-receipt',str(C/'application_receipt.json'),'--current-observations',str(C/'applied_state_observations.parquet'),'--expected-current-observations-sha256',cr['output_pins']['applied_state_observations.parquet']['sha256'],'--delivery-output-dir',str(D),'--retain-existing-as-stage','65','--expected-existing-effective-sha256','08c4b80244b8dd9f7de2c0beaf0e0a0e7b5b0e6ae186c9049babfff5ccec1d03']
prior=json.loads((E/'next_overlay_application_20261008/application_receipt.json').read_text())['claim_input_pins']
prior[str(E/'residual_source_followup_20261008/accepted_county_bound_primary2010_addon_8.csv.gz')]='e381587945a8fb8bf913233f351d13c1682fbe6630cfd84d775e31f88f5029d2'
prior[str(E/'residual_source_followup_20261008/accepted_all_regions_county_bound_primary2010_addon_127.csv.gz')]='0f17caea9cc1191f70d2944b22ea4a657215822d14d312b31b49e8daca487f72'
prior[str(E/'official_population_residual_sources_20261008/next65_source_gap/corrected_cell_role_ready_primary2010_claims.csv.gz')]='81b83a2aa32a2aae702067b88a6a75f94bbf3caa3d84d95df6b2c802b5425821'
prior[str(E/'official_population_residual_sources_20261008/next65_source_gap/accepted_direct_county_Krasnodar8_primary2010_addon.csv.gz')]='edeb944d19901e670348beae66bbd0d55900512ad6233bf6bc87441ddf791fd4'
for path,sh in prior.items():args.extend(['--claim-file',path,'--expected-claim-sha256',sh])
with (Z/'execution.log').open('w') as log:subprocess.run(args,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Applied1961claims after canonical66; see application_receipt.json')
