"""Execute the reviewed7049 overlay only after the actual canonical67 export."""
from pathlib import Path
import json,subprocess,sys,hashlib
Z=Path(__file__).resolve().parent;E=Z.parent;R=E.parents[1];D=Path('/workspace/settlements-delivery/working-full-chain-20261007')
export=json.loads((E/'working_full_chain_20261007/export_receipt.json').read_text());assert export['working_stage']==68
C=E/'main_axis_residual_application68_20261008';cr=json.loads((C/'application_receipt.json').read_text());assert cr['intended_working_stage']==68 and cr['canonical_State_API_replay_passed']
args=[sys.executable,str(Z/'apply_cumulative_primary_overlay.py'),'--stage','68','--main',export['file'],'--expected-main-sha256',export['sha256'],'--primary-credit-roster',str(C/'applied_primary_credited_UID_roster.csv.gz'),'--expected-credit-sha256',cr['output_pins']['applied_primary_credited_UID_roster.csv.gz']['sha256'],'--composer-receipt',str(C/'application_receipt.json'),'--current-observations',str(C/'applied_state_observations.parquet'),'--expected-current-observations-sha256',cr['output_pins']['applied_state_observations.parquet']['sha256'],'--delivery-output-dir',str(D),'--retain-existing-as-stage','67','--expected-existing-effective-sha256','167e492ba0373b126602ed5c16d3eb01b3be6e5b631e0b2dbd70fa6b7bedd281']
prior=json.loads((E/'next_overlay_application_20261008/application_receipt.json').read_text())['claim_input_pins']
prior[str(E/'residual_source_followup_20261008/accepted_county_bound_primary2010_addon_8.csv.gz')]='e381587945a8fb8bf913233f351d13c1682fbe6630cfd84d775e31f88f5029d2'
prior[str(E/'residual_source_followup_20261008/accepted_all_regions_county_bound_primary2010_addon_127.csv.gz')]='0f17caea9cc1191f70d2944b22ea4a657215822d14d312b31b49e8daca487f72'
prior[str(E/'official_population_residual_sources_20261008/next65_source_gap/corrected_cell_role_ready_primary2010_claims.csv.gz')]='81b83a2aa32a2aae702067b88a6a75f94bbf3caa3d84d95df6b2c802b5425821'
prior[str(E/'official_population_residual_sources_20261008/next65_source_gap/accepted_direct_county_Krasnodar8_primary2010_addon.csv.gz')]='edeb944d19901e670348beae66bbd0d55900512ad6233bf6bc87441ddf791fd4'
prior[str(E/'next67_primary_source_routes/ready_primary2010_regional_claims.csv.gz')]='c62ecf6f8b23088c79c230e79a3600062f2c6b7a0025378f25fa30c2b133378c'
prior[str(E/'next68_primary_source_routes/ready_primary2010_regional_claims.csv.gz')]='e7bfd157ee1cd122b6a34d89f0871c5e97af4f0aa4ed8a6af9d16a0f1b842f1e'
for path,sh in prior.items():args.extend(['--claim-file',path,'--expected-claim-sha256',sh])
with (Z/'execution.log').open('w') as log:subprocess.run(args,check=True,stdout=log,stderr=subprocess.STDOUT)
print('Applied7049claims after canonical68; see application_receipt.json')
