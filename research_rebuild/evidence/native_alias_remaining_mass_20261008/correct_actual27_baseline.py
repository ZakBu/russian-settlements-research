import sys,json,importlib.util
from pathlib import Path
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
O=Path(__file__).parent;p=O/'application_receipt.json';r=json.loads(p.read_text());old_before=r['before'];old_after=r['after'];old_bf=r['before_finite_all3_all_points'];old_af=r['after_finite_all3_all_points']
for x,h in r['input_pins'].items():assert sha(Path(x))==h,x
for x,h in r['output_pins'].items():assert sha(O/x)==h,x
s=load(27)
sp=importlib.util.spec_from_file_location('fm',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm)
r['before']=s.metrics();r['before_finite_all3_all_points']=fm.finite_metrics(s);s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);r['after']=s.metrics();r['after_finite_all3_all_points']=fm.finite_metrics(s)
bf,af=r['before_finite_all3_all_points'],r['after_finite_all3_all_points'];r['net_finite_all3_all_points']={'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']}}
r['baseline_correction']={'reason':'Preparation ran before loader27 integration; load(27) then replayed actual26. Pinned source proofs, accepted edges and points unchanged. Corrected receipt uses actual integrated27 and the same accepted3 CSVs.','previous_mislabeled_before':old_before,'previous_mislabeled_after':old_after,'previous_before_finite':old_bf,'previous_after_finite':old_af,'exact_before_covered_population_difference':{y:r['before'][y]['covered_population']-old_before[y]['covered_population'] for y in r['before']},'source_and_output_pins_unchanged':True}
p.write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({'baseline_correction':r['baseline_correction']['exact_before_covered_population_difference'],'net':r['net_finite_all3_all_points']},ensure_ascii=False))
