"""Replay fixed own-function co-presence using newly admitted strict source counts."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 oldp=ROOT/'typology2021_cycle05/own_function_rules/settlement_own_function_evidence_2021.parquet';ps={f:ROOT/f'model_inputs_cycle07/institutional_relink477_v1/{f}/settlement_features_full_axis.parquet'for f in ['commerce','education','medical']};protocol={'status':'PROSPECTIVE_FIXED_FUNCTION_REPLAY_BEFORE_SOURCE_VALUES','old_features_sha256':sha(oldp),'new_inputs_sha256':{str(p.relative_to(ROOT)):sha(p)for p in ps.values()},'rules':'Exactly old upper-seat +school+general clinic and physical trade/government co-presence. ALL-local-admin provider expansion does not change this thematic rule. Same positive-only flags; developed agro infrastructure remains NA. No mass alteration.'};(H/'own_functions_supplemental_protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
 old=pd.read_parquet(oldp);f=old.copy();cs={'commerce':{'own2021_strict_large_retail_source_sites':'services_osm2021_large_retail_baseline_count','own2021_strict_physical_administration_source_sites':'services_osm2021_administration_baseline_count'},'education':{'own2021_strict_school_source_sites':'education_osm2021_school_baseline_count'},'medical':{'own2021_strict_general_clinical_source_sites':'medical_osm_baseline_healthcare_sites_count'}}
 for fam,cols in cs.items():
  z=pd.read_parquet(ps[fam]);assert z.id.equals(f.id)
  for c,k in cols.items():f[c]=z[k]
 seat=f.admin2021_upper_municipal_center_evidence.eq(True).fillna(False);trade=f.own2021_strict_large_retail_source_sites.gt(0);gov=f.own2021_strict_physical_administration_source_sites.gt(0);school=f.own2021_strict_school_source_sites.gt(0);general=f.own2021_strict_general_clinical_source_sites.gt(0)
 for c,v in {'trade_and_administration_function_evidence':trade&gov,'basic_administrative_service_function_evidence':seat&school&general,'basic_administrative_service_with_physical_admin_evidence':seat&school&general&gov}.items():f[c]=pd.array(np.where(v,True,None),dtype='boolean')
 changes=[]
 for c in old.columns.drop('id'):
  same=old[c].eq(f[c]).fillna(False)|(old[c].isna()&f[c].isna())
  for j in np.flatnonzero(~same.to_numpy()):changes.append({'id':f.id.iloc[j],'field':c,'old_value':str(old[c].iloc[j]),'new_value':str(f[c].iloc[j])})
 f.to_parquet(H/'settlement_own_function_evidence_2021.parquet',index=False);pd.DataFrame(changes,columns=['id','field','old_value','new_value']).to_parquet(H/'own_function_changed_cells.parquet',index=False);r={'status':'ACTUAL_FIXED_RULE_REPLAY_PENDING_INDEPENDENT_REVIEW','changed_cells':len(changes),'changed_NPs':len(set(x['id']for x in changes)),'protocol_sha256':sha(H/'own_functions_supplemental_protocol.json'),'features_sha256':sha(H/'settlement_own_function_evidence_2021.parquet'),'admin_rule_unchanged':True,'mass_untouched':True};(H/'own_function_replay_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
