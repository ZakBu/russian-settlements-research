"""Remove duplicated candidate context from the accepted witness, retaining frozen keyed references."""
from pathlib import Path
import json,hashlib,pandas as pd
O=Path(__file__).parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for filename in ['positive_literal_native_county_ownpoint_candidates.csv.gz','all_native_name_type_county_competitors.csv.gz']:
 data=pd.read_csv(O/filename,dtype=str,keep_default_na=False)
 data.to_csv(O/filename,index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
p=O/'accepted_native_source_binding_witnesses.csv.gz';f=pd.read_csv(p,keep_default_na=False)
for c in ['county_source_anchors_json','old_native_two_sided_source_bracket_json','current_native_two_sided_source_bracket_json']:
 if c in f:f=f.drop(columns=[c])
f['full_literal_sourcecounty_anchor_and_bracket_witness_file']='positive_literal_native_county_ownpoint_candidates.csv.gz'
f['full_literal_sourcecounty_anchor_and_bracket_witness_sha256']=sha(O/'positive_literal_native_county_ownpoint_candidates.csv.gz')
f['full_literal_sourcecounty_anchor_and_bracket_witness_key_column']='native2010_source_record_id'
f['actual_boundary_checks_file']='actual_source_anchor_boundary_checks.csv.gz'
f.to_csv(p,index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
rawpath=O/'actual_native_raw_source_checks.csv.gz'
raw=pd.read_csv(rawpath,keep_default_na=False).sort_values(['source_file','source_locator','source_record_id'])
raw.to_csv(rawpath,index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
holdpath=O/'application_holds.csv.gz'
hold=pd.read_csv(holdpath,keep_default_na=False)
hold=hold.drop(columns=[c for c in ['county_source_anchors_json','old_native_two_sided_source_bracket_json','current_native_two_sided_source_bracket_json'] if c in hold])
hold['full_literal_context_witness_file']='positive_literal_native_county_ownpoint_candidates.csv.gz'
hold['full_literal_context_witness_sha256']=sha(O/'positive_literal_native_county_ownpoint_candidates.csv.gz')
hold.to_csv(holdpath,index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
r=json.loads((O/'application_receipt.json').read_text());r['output_pins'][p.name]=sha(p);r['output_pins'][rawpath.name]=sha(rawpath);r['output_pins'][holdpath.name]=sha(holdpath);r['input_pins'][str((O/'compact.py').resolve())]=sha(O/'compact.py');
for filename in ['positive_literal_native_county_ownpoint_candidates.csv.gz','all_native_name_type_county_competitors.csv.gz']:r['input_pins'][str((O/filename).resolve())]=sha(O/filename)
r['input_pins'][str((O/'scan.py').resolve())]=sha(O/'scan.py');r['input_pins'][str((O/'scan_receipt.json').resolve())]=sha(O/'scan_receipt.json');r['input_pins'][str(Path('/workspace/russian-settlements-research/research_rebuild/mass_linkage/apply_unique_county_name_bridge_20261007.py'))]=sha(Path('/workspace/russian-settlements-research/research_rebuild/mass_linkage/apply_unique_county_name_bridge_20261007.py'))
r['input_pins'][str((O/'audit_county.py').resolve())]=sha(O/'audit_county.py');r['input_pins'][str((O/'rivals.py').resolve())]=sha(O/'rivals.py');r['input_pins'][str((O/'verify.py').resolve())]=sha(O/'verify.py')
for filename in ['nearest_true_county_hierarchy_checks.csv.gz','county_hierarchy_audit_receipt.json','all_2010_regional_name_type_rivals.csv.gz']:r['output_pins'][filename]=sha(O/filename)
r['county_hierarchy_audit']=json.loads((O/'county_hierarchy_audit_receipt.json').read_text())
r['input_pins'].pop(str((O/'ranked_remaining2010_mass.csv.gz').resolve()),None)
r['input_pins'][str((O/'prepare_application.py').resolve())]=sha(O/'prepare_application.py')
r['accepted_witness_compaction']='Redundant full anchor/bracket arrays referenced through frozen original candidate file by exact native2010 source ID, retaining all rival/context evidence and all actual boundary checks; no accepted ledger edited.'
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(p.stat().st_size)
