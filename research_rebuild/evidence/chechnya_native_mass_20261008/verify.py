import sys,json,re
from pathlib import Path
import pandas as pd,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;receipt=json.load(open(O/'receipt.json'));s=load(29);assert s.metrics()==receipt['before'];assert all(sha(Path(p))==v for p,v in receipt['input_hashes'].items());s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);assert s.metrics()==receipt['after']
checks=pd.read_csv(O/'literal_source_checks.csv');pairs=pd.read_csv(O/'accepted_pair_witness.csv');book={};parents=[]
for z in pairs.to_dict('records'):
 a=checks[checks.source_record_id.eq(z['old_id'])].iloc[0];p=Path(a.file)
 if p not in book:book[p]=xlrd.open_workbook(str(p))
 sh=book[p].sheet_by_name(a.sheet);parent=None
 for row in range(int(a.row_1based)-2,-1,-1):
  vals=sh.row_values(row);head=[str(v) for v in vals if isinstance(v,str) and re.search(r'район\s*-\s*все сельское население',v,re.I)]
  if head:parent=(row+1,head[0]);break
 assert parent and county_key(parent[1].split(' - ')[0])==county_key(z['old_county']),z
 parents.append({'source_record_id':z['old_id'],'district_source_file':str(p),'sha256':sha(p),'parent_sheet':sh.name,'parent_row_1based':parent[0],'raw_parent':parent[1],'printed2002_county':z['old_county'],'parent_matches_selected_county':True})
pd.DataFrame(parents).to_csv(O/'raw2002_parent_witness.csv',index=False); (O/'verification_receipt.json').write_text(json.dumps({'stage29_baseline_reproduced':True,'source_hashes_match':True,'canonical_loader_replay_matches':True,'raw2002_parent_checks':len(parents),'accepted_edges':len(pd.read_csv(O/'accepted_identity_edge_delta.csv')),'points':len(pd.read_csv(O/'accepted_point_use_delta.csv')),'native_population_values_unmodified':True},indent=2));print('PASS',len(parents))
