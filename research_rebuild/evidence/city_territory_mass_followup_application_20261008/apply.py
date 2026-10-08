from pathlib import Path
import pandas as pd,json,hashlib,shutil
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence');I=E/'city_territory_mass_followup_20261008';O=Path(__file__).parent;O.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
STATUS='applied_complete_published_city_territorial_scope';axis='published_complete_city_territory_scope'
config=[('candidate_group_observations.csv','accepted_group_observations.csv'),('candidate_constituent_credit_union.csv','accepted_constituent_credit_union.csv'),('candidate_representative_scope_points.csv','accepted_representative_scope_points.csv'),('candidate_scope_edges.csv','accepted_scope_edges.csv')]
for src,dst in config:
 d=pd.read_csv(I/src,keep_default_na=False);d['candidate_only']=False;d['decision_status']=STATUS;d['identity_axis']=axis;d['source_grain']='city_with_published_subordinates';d['boundary_comparability']='UNKNOWN';d['ordinary_same_place']=False;d['exact_annexation_roster_claimed']=False;d['legal_annexation_asserted']=False;d['historical_constituent_own_point_asserted']=False;d['historical_individual_point_asserted']=False
 if 'point_role' in d:d['point_role']='representative_scope'
 if 'scope_point_role' in d:d['scope_point_role']='representative_scope'
 if src=='candidate_group_observations.csv':
  assert d.group.nunique()==3 and len(d)==9
  for group,g in d.groupby('group'):assert set(g.census_year)=={2002,2010,2021} and g.roster_complete.all()
 if src=='candidate_constituent_credit_union.csv':
  assert len(d)==527 and d.source_record_id.is_unique and d.source_population_unmodified.all();d['additive_only_within_complete_published_year_group']=True;d['separate_population_credit_in_addition_to_group']=False
 if src=='candidate_representative_scope_points.csv':assert len(d)==3 and d.group.is_unique
 if src=='candidate_scope_edges.csv':assert len(d)==6;d['event_relations_effective_date']='UNKNOWN'
 d.to_csv(O/dst,index=False)
for name in ['printed_controls_atomic_conservation.csv','complete_scope_source_witnesses.csv','original_atomic_raw_row_bindings.csv','net_source_ID_union_potential.csv']:
 shutil.copy(I/name,O/name)
n=pd.read_csv(I/'net_source_ID_union_potential.csv');assert dict(n.groupby('year').new_native_population_if_scope_admitted.sum())=={2002:61799,2010:7482,2021:1860};assert dict(n.groupby('year').unique_new_source_IDs.sum())=={2002:55,2010:47,2021:33}
r=json.loads((I/'candidate_receipt.json').read_text());r.update(status=STATUS,identity_axis=axis,source_grain='city_with_published_subordinates',candidate_only=False,admission_stage=28,source_values_modified=False,ordinary_graph_changed=False,ordinary_point_uses_changed=False,legal_annexation_asserted=False,point_role='representative_scope',historical_individual_point_asserted=False,root_authorization='Root explicitlyapproved all3 complete published territorialhierarchy scopes as separate changing territorialtraces; no exactannexation/ordinaryNP identity claim.',input_packet_sha256={str(I/src):sha(I/src) for src,_ in config}|{str(I/'candidate_receipt.json'):sha(I/'candidate_receipt.json')},outputs={p.name:sha(p) for p in O.glob('*.csv')});r['net_gain']=r.pop('net_gain_by_year');(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:r[k] for k in ['status','groups','observations','atomic_members','net_gain','identity_axis']},ensure_ascii=False))
