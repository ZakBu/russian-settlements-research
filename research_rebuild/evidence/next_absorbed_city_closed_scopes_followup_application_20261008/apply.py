from pathlib import Path
import pandas as pd,json,hashlib,shutil
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence');I=E/'next_absorbed_city_closed_scopes_followup_20261008';O=Path(__file__).parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r=json.loads((I/'candidate_receipt.json').read_text());assert r['frozen_review_packet'] and r['baseline_loader_stage']==37
for name,h in r['outputs'].items():assert sha(I/name)==h
for path,h in r['source_manifest'].items():assert sha(path)==h
STATUS='applied_complete_published_city_territorial_scope';axis='published_complete_city_territory_scope'
for stem in ['group_observations','constituent_credit_union','representative_scope_points','scope_edges']:
 d=pd.read_csv(I/('candidate_'+stem+'.csv'),keep_default_na=False)
 d['candidate_only']=False;d['decision_status']=STATUS;d['identity_axis']=axis;d['source_grain']='city_with_published_subordinates';d['boundary_comparability']='UNKNOWN';d['ordinary_same_place']=False;d['exact_annexation_roster_claimed']=False;d['legal_annexation_asserted']=False;d['historical_constituent_own_point_asserted']=False;d['historical_individual_point_asserted']=False
 if 'point_role' in d:d['point_role']='representative_scope'
 if 'scope_point_role' in d:d['scope_point_role']='representative_scope'
 if stem=='group_observations':assert len(d)==9 and d.group.nunique()==3 and d.roster_complete.all()
 if stem=='constituent_credit_union':
  assert len(d)==26 and d.source_record_id.is_unique and d.source_population_unmodified.all();d['additive_only_within_complete_published_year_group']=True;d['separate_population_credit_in_addition_to_group']=False
 if stem=='representative_scope_points':assert len(d)==3 and d.group.is_unique
 if stem=='scope_edges':assert len(d)==6;d['event_relations_effective_date']='UNKNOWN'
 d.to_csv(O/('accepted_'+stem+'.csv'),index=False)
for name in ['printed_controls_atomic_conservation.csv','complete_scope_source_witnesses.csv','original_atomic_raw_row_bindings.csv','original2002_2010_complete_city_rural_block_closures.csv','actual_published_auxiliary_atom.csv','net_source_ID_union_potential.csv','held_group_scope.csv']:
 shutil.copy(I/name,O/name);assert sha(O/name)==sha(I/name)
a=pd.read_csv(O/'actual_published_auxiliary_atom.csv',keep_default_na=False);assert len(a)==1 and a.iloc[0].population==6 and a.iloc[0].selected_source_record_id=='' and not a.iloc[0].national_additive_credit
m=pd.read_csv(O/'accepted_constituent_credit_union.csv');o=pd.read_csv(O/'accepted_group_observations.csv')
for z in o.itertuples():
 own=m[m.group.eq(z.group)&m.census_year.eq(z.census_year)];aux=a[a.group.eq(z.group)&a.census_year.eq(z.census_year)]
 assert len(own)==z.constituent_count and int(own.population.sum())==int(z.native_selected_population_sum) and int(own.population.sum()+aux.population.sum())==int(z.population) and set(own.source_record_id)==set(json.loads(z.source_record_ids_json))
n=pd.read_csv(O/'net_source_ID_union_potential.csv');assert n.groupby('year').new_native_population_if_scope_admitted.sum().to_dict()=={2002:49106,2010:5,2021:4}
c=pd.read_csv(O/'printed_controls_atomic_conservation.csv');assert c[c.year.isin([2002,2021])].difference_not_allocated.eq(0).all();assert c[c.year.eq(2010)].set_index('group').difference_not_allocated.to_dict()=={'published_closed_city_scope_Тольятти':0,'published_closed_city_scope_Улан_Удэ':0,'published_closed_city_scope_Пермь':-3}
r.update(status=STATUS,candidate_only=False,identity_axis=axis,source_grain='city_with_published_subordinates',ordinary_graph_changed=False,ordinary_point_uses_changed=False,legal_annexation_asserted=False,point_role='representative_scope',historical_individual_point_asserted=False,root_loader_integration_pending=True,baseline_loader_stage=37,baseline37_net_not_future_report_witness=True,root_authorization='Root explicitly approved3 complete published sourceyear city-associated territorial scopes: Tolyatti,UlanUde,Perm. Perm actualraw6aux blankID nonadditive retained; protectedcontroldiff-3 unallocated. No ordinarysameplace, legalannexation, modernboundarysum or county childpoint projection.',input_packet_sha256={str(I/p):sha(I/p) for p in r['outputs']}|{str(I/'candidate_receipt.json'):sha(I/'candidate_receipt.json')})
r['net_gain_against_explicit_baseline37']=r.pop('net_gain_by_year');r['net_gain']=r['net_gain_against_explicit_baseline37'];r['outputs']={p.name:sha(p) for p in O.glob('*.csv')};r['code_sha256']={'apply.py':sha(O/'apply.py')};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
(O/'README.md').write_text('Applied3 complete sourceyear city-associated territorial scopes: Tolyatti/UlanUde/Perm,9observations26native refs,3owncity representative_scope points,6territorial edges. Explicit baseline37exclusive gains49106/5/4; integrated report recalculates native UID union. Original raw controls/proofs copied unchanged;18native XLS atoms and whole02/10rosters reopened. Perm actual6-person secondary raw leaf absent selected layer is blankID/nonadditive nationally, without own historical point; native991167+actual6=991173 versus primary991170, difference-3 preserved unallocated. No ordinarysameplace, legalannexation, modernboundary reconstruction or county representative projection. Four other cities held with sourcegrain reasons. Root loader integration pending separately.\n')
print(json.dumps({k:r[k] for k in ['status','groups','observations','atomic_members','net_gain']},ensure_ascii=False))
