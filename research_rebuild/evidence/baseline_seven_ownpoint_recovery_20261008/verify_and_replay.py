import sys,json,hashlib,importlib.util,time,csv,re
from pathlib import Path
import pandas as pd
Z=Path(__file__).resolve().parent;E=Z.parent;sys.path.insert(0,str(Z.parents[1]/'mass_linkage'))
from working_state_20261007 import load
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
spec=importlib.util.spec_from_file_location('finite_helper',E/'working_full_chain_20261007/replay_additional_native_20261008.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
pins=json.loads((Z/'input_pins.json').read_text());assert all(sha(p)==h for p,h in pins.items());s=load(56);before=m.finite(s);native_before=s.obs[['source_record_id','population','source_quality']].copy() if 'source_quality' in s.obs else s.obs[['source_record_id','population']].copy();edges_before=dict(s.uf.parent);reject=pd.read_csv(Z/'rejected_point_uses.csv');point=pd.read_csv(Z/'accepted_point_use_delta.csv.gz');w=json.loads((Z/'native_point_witnesses.json').read_text())
# Independent literal CSV source parsing and classifier raw lines, bypass derived binding projection.
raw_path=Path(point.point_origin_file.iloc[0]);targets={v['literal_TSV_line_1based']:v for v in w};actual={}
with raw_path.open() as stream:
 for n,row in enumerate(csv.DictReader(stream,delimiter='\t'),2):
  if n in targets: actual[n]=row
for n,v in targets.items():
 assert actual[n]==v['literal_TSV_row'];assert actual[n]['?oktmo'].strip('"').lstrip('0')==v['native_own_OKTMO'].lstrip('0')
for r in point.itertuples():
 candidates=[v for v in w if v['carrier_source_record_id']==r.point_source_record_id];assert candidates
 assert any(re.search(r'POINT\(([-\d.]+) ([-\d.]+)\)',v['literal_TSV_row']['?coord']) and float(re.search(r'POINT\(([-\d.]+) ([-\d.]+)\)',v['literal_TSV_row']['?coord'])[1])==r.longitude and float(re.search(r'POINT\(([-\d.]+) ([-\d.]+)\)',v['literal_TSV_row']['?coord'])[2])==r.latitude for v in candidates)
assert len(reject)==21 and len(point)==18 and reject.target_source_record_id.nunique()==21 and point.target_source_record_id.nunique()==18
s.reject_point_uses(Z/'rejected_point_uses.csv');rejected=m.finite(s);s.add_deltas(point_paths=[Z/'accepted_point_use_delta.csv.gz']);after=m.finite(s);assert edges_before==dict(s.uf.parent);assert native_before.equals(s.obs[native_before.columns]);assert all(s.point_rows[x]['point_origin_file']==str(raw_path) for x in point.target_source_record_id)
receipt=dict(status='verified_frozen_point_claim_recovery_only',source_state_stage=56,prior_git55_control='fce754a35ddd2a182b242d6d415797e177860532',carriers_rejected=7,point_claims_rejected=21,carriers_recovered=6,accepted_point_uses=18,held_unpointed_carriers=1,finite_before=before,finite_after_rejection=rejected,finite_after_recovery=after,net_finite_population_delta={y:after['populations_by_year'][y]-before['populations_by_year'][y] for y in before['populations_by_year']},native_population_quality_source_ids_unchanged=True,identity_graph_unchanged=True,limitations=['Роща own entity lacks cached coordinates; all three coordinate claims withheld pending own physical disambiguation.','Cached entity snapshot points used retrospectively for earlier census records on accepted identities; no census-day accuracy claim.','Own code evidence and locality classifier evidence are explicit independent-source interpretation; no provider code correction rewrites raw rows.'],input_pins=pins,output_pins={p.name:sha(p) for p in [Z/'rejected_point_uses.csv',Z/'accepted_point_use_delta.csv.gz',Z/'native_point_witnesses.json',Z/'held_carriers.csv']},executed_verifier_code_sha256=sha(Path(__file__)),state_inputs={str(p):sha(p) for p in s.inputs})
(Z/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');(Z/'verification_receipt.json').write_text(json.dumps({k:receipt[k] for k in ['status','source_state_stage','finite_before','finite_after_rejection','finite_after_recovery','net_finite_population_delta','native_population_quality_source_ids_unchanged','identity_graph_unchanged','output_pins','executed_verifier_code_sha256']},indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['finite_before','finite_after_rejection','finite_after_recovery','net_finite_population_delta']},indent=2))
