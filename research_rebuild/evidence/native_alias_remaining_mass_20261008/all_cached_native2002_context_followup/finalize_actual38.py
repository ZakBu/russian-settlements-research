import json,sys,shutil,importlib.util
from pathlib import Path
import pandas as pd
O=Path(__file__).parent
R=Path('/workspace/russian-settlements-research')
sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha
archive=O/'original_actual37_candidate_before_current_namesake_hold';archive.mkdir(exist_ok=True)
if not (archive/'application_receipt.json').exists():
 r=json.loads((O/'application_receipt.json').read_text())
 for name in ['application_receipt.json']+list(r['output_pins']):shutil.copy2(O/name,archive/name)
r=json.loads((archive/'application_receipt.json').read_text())
old='2002:013_2dd2afccd6_02c_Smolenskaja.xls:Sheet1:3248'
current='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:124500'
for name,col,value in [('accepted_source_bindings.csv.gz','old_source_record_id',old),('accepted_identity_edge_delta.csv','from_source_record_id',old),('accepted_point_use_delta.csv','target_source_record_id',old)]:
 d=pd.read_csv(archive/name,dtype=str,keep_default_na=False);d=d[d[col].ne(value)];d.to_csv(O/name,index=False,compression='gzip' if name.endswith('.gz') else None)
hold={'old_source_record_id':old,'rejected_proposed_current_source_record_id':current,'competing_current_source_record_id':'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:124501','reason':'Distinct same-class current Kozlovka villages share publisher OKATO66236000153 and coordinates. Old24-person row has no independently bound own point/code/date proof distinguishing the765-person proposed target from the separate24-person current village. No census identity or point use admitted.'}
(O/'current_namesake_hard_hold.json').write_text(json.dumps(hold,ensure_ascii=False,indent=2))
s=load(38)
spec=importlib.util.spec_from_file_location('app',O/'apply.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
before=s.metrics();bf=app.finite_metrics(s)
for path,h in r['input_pins'].items():assert sha(Path(path))==h,path
# Reuse the bounded all-current-namesake guard on actual38 without another loader replay.
checker=(O/'finish_current_competitors_and_replay.py').read_text()
start=checker.index("f=pd.read_csv(O/'accepted_source_bindings.csv.gz'")
end=checker.index(";r['output_pins']['all_current_named_competitors.csv.gz']")
exec(checker[start:end],dict(O=O,s=s,pd=pd,json=json,**{k:getattr(__import__('current_chain_state_20261007',fromlist=[k]),k) for k in ['normalize','distance_km']}))
f=pd.read_csv(O/'accepted_source_bindings.csv.gz',dtype=str,keep_default_na=False);overlap=[]
for z in f.to_dict('records'):
 a=s.uf.find(z['old_source_record_id']);b=s.uf.find(z['current_source_record_id'])
 assert a!=b and s.years[a]=={2002} and s.years[b]=={2010,2021},z['name']
 overlap.append({'old_source_record_id':z['old_source_record_id'],'current_source_record_id':z['current_source_record_id'],'actual38_old_component_years':'[2002]','actual38_current_component_years':'[2010, 2021]','disjoint':True})
pd.DataFrame(overlap).to_csv(O/'actual38_overlap_checks.csv.gz',index=False,compression='gzip')
s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv'])
after=s.metrics();af=app.finite_metrics(s)
net={'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in ['2002','2010','2021']}}
assert net=={'histories':5,'populations_by_year':{'2002':4896,'2010':6425,'2021':5975}},net
r.update(baseline_stage=38,status='Frozen actual38 source/output-pinned native02 CSV replay passed; five histories ready for stage39',accepted_cases=5,edges=5,point_uses=3,holds=250,before=before,after=after,before_finite_all3_all_points=bf,after_finite_all3_all_points=af,net_finite_all3_all_points=net,all_current_namesakes_checked_before_component_filter=True)
r['original_actual37_candidate_archive']='original_actual37_candidate_before_current_namesake_hold'
r['original_actual37_candidate_status']='Six source-positive candidates replayed before current-homonym guard; one Kozlovka identity held by final independent guard. Not six accepted physical identities.'
names=list(r['output_pins'])+['all_current_named_competitors.csv.gz','actual38_overlap_checks.csv.gz','current_namesake_hard_hold.json']
r['output_pins']={name:sha(O/name) for name in names}
r['original_actual37_archive_pins']={name:sha(archive/name) for name in ['application_receipt.json']+list(json.loads((archive/'application_receipt.json').read_text())['output_pins'])}
r['current_namesake_rows_checked']=len(pd.read_csv(O/'all_current_named_competitors.csv.gz'))
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
code=(O/'apply.py').read_text().replace('stage37','stage38').replace('actual37','actual38').replace('Actual37','Actual38').replace('load(37)','load(38)');(O/'apply.py').write_text(code)
print(json.dumps({'baseline':38,'accepted':5,'edges':5,'points':3,'before_finite':bf,'after_finite':af,'net':net,'receipt_sha256':sha(O/'application_receipt.json')},ensure_ascii=False))
