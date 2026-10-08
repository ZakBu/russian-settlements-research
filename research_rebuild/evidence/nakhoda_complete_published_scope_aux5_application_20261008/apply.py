from pathlib import Path
import pandas as pd,json,hashlib,shutil,xlrd
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence');I=E/'nakhoda_complete_published_scope_aux5_20261008';O=Path(__file__).parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
STATUS='applied_complete_published_city_territorial_scope';axis='published_complete_city_territory_scope'
r=json.loads((I/'candidate_receipt.json').read_text())
for name,h in r['outputs'].items():assert sha(I/name)==h
for path,h in r['source_manifest'].items():assert sha(path)==h
aux=pd.read_csv(I/'actual_primary_auxiliary2002_atom.csv',keep_default_na=False);a=aux.iloc[0];raw=xlrd.open_workbook(a.raw_file).sheet_by_name(a.raw_sheet).row_values(int(a.raw_row_1based)-1)
assert len(aux)==1 and a.selected_source_record_id=='' and int(a.population)==5 and not a.national_additive_credit
assert raw[1].strip()==a.raw_label=='маяк Поворотный' and int(raw[2])==5
config=[('candidate_group_observations.csv','accepted_group_observations.csv'),('candidate_constituent_credit_union.csv','accepted_constituent_credit_union.csv'),('candidate_representative_scope_points.csv','accepted_representative_scope_points.csv'),('candidate_scope_edges.csv','accepted_scope_edges.csv')]
for src,dst in config:
 d=pd.read_csv(I/src,keep_default_na=False)
 if 'source_record_id' in d:
  d=d[d.source_record_id.ne('')].copy();assert len(d)==14 and d.source_record_id.is_unique
  assert d.source_population_unmodified.all() and d.exclusive_source_ID_credit.all()
  d['additive_only_within_complete_published_year_group']=True;d['separate_population_credit_in_addition_to_group']=False
 if src=='candidate_group_observations.csv':
  assert len(d)==3 and set(d.census_year)=={2002,2010,2021}
  d['actual_primary_atomic_constituent_count']=d.constituent_count.astype(int);d['constituent_count']=d.native_selected_member_count.astype(int)
  for rr in d.itertuples():assert int(rr.native_selected_population_sum)+int(rr.actual_primary_auxiliary_population_sum)==rr.population
 d['candidate_only']=False;d['decision_status']=STATUS;d['identity_axis']=axis;d['source_grain']='city_with_published_subordinates';d['boundary_comparability']='UNKNOWN';d['ordinary_same_place']=False;d['exact_annexation_roster_claimed']=False;d['legal_annexation_asserted']=False;d['historical_constituent_own_point_asserted']=False;d['historical_individual_point_asserted']=False
 if 'point_role' in d:d['point_role']='representative_scope'
 if 'scope_point_role' in d:d['scope_point_role']='representative_scope'
 if src=='candidate_scope_edges.csv':d['event_relations_effective_date']='UNKNOWN'
 d.to_csv(O/dst,index=False)
for name in ['actual_primary_auxiliary2002_atom.csv','printed_controls_atomic_conservation.csv','complete_scope_source_witnesses.csv','original_atomic_source_row_verification.csv','net_source_ID_union_potential.csv']:shutil.copy(I/name,O/name)
obs=pd.read_csv(O/'accepted_group_observations.csv',keep_default_na=False);m=pd.read_csv(O/'accepted_constituent_credit_union.csv',keep_default_na=False)
for rr in obs.itertuples():
 own=m[m.census_year.eq(rr.census_year)];assert len(own)==rr.constituent_count and int(own.population.sum())+int(rr.actual_primary_auxiliary_population_sum)==rr.population;assert set(own.source_record_id)==set(json.loads(rr.source_record_ids_json))
assert list(obs.sort_values('census_year').population)==[178813,160760,141035]
r.update(status=STATUS,candidate_only=False,identity_axis=axis,source_grain='city_with_published_subordinates',atomic_members=14,actual_primary_atomic_members=15,admission_stage=27,ordinary_graph_changed=False,ordinary_point_uses_changed=False,legal_annexation_asserted=False,point_role='representative_scope',historical_individual_point_asserted=False,root_authorization='Root explicitly approved complete published Nakhoda territorial scope with actual primary auxiliary5 preserved nonadditive; no invented selectedID, no exact annexation or ordinaryNP identity claim.',input_packet_sha256={str(I/p):sha(I/p) for p in r['outputs']}|{str(I/'candidate_receipt.json'):sha(I/'candidate_receipt.json')})
r['net_gain']=r.pop('net_gain_by_year');r['outputs']={p.name:sha(p) for p in O.glob('*.csv')};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
(O/'README.md').write_text('Approved complete published Nakhoda territorial scope: 178813 / 160760 / 141035. Native selected members14; actual primary atomic members15. The original primary 2002 маяк Поворотный5 is retained in actual_primary_auxiliary2002_atom.csv with blank selectedID and zero national additive credit. Native selected credit gain28864 /0/0. Observation constituent_count counts native members; actual_primary_atomic_constituent_count includes the auxiliary. Complete population equals native_selected_population_sum plus actual_primary_auxiliary_population_sum. Boundaries UNKNOWN; current representative scope point; no ordinary NP, exact legal annexation, or historical individual coordinate assertion. All source roster/control/quality witnesses pinned in receipt.\n')
print(json.dumps({k:r[k] for k in ['status','atomic_members','actual_primary_atomic_members','net_gain']},ensure_ascii=False))
