from pathlib import Path
import pandas as pd,re,json,hashlib,math
O=Path(__file__).parent;D=pd.read_pickle('/dev/shm/over500-20261009/east_enriched.pkl');R=pd.read_csv(O/'assigned.csv').fillna('');P=pd.read_parquet('/dev/shm/over500-20261009/points_compact.parquet').fillna('').drop_duplicates('target_source_record_id',keep='last').set_index('target_source_record_id');by=D.set_index('source_record_id',drop=False)
# Apply the frozen first batch locally as checked anchors; root loader remains unchanged.
E1=pd.read_csv(O.parent/'accepted_identity_edge_delta.csv');P1=pd.read_csv(O.parent/'accepted_point_use_delta.csv').fillna('');par={}
def find(a):
 if a not in par:par[a]=a
 if par[a]!=a:par[a]=find(par[a])
 return par[a]
for e in E1.itertuples():par[find(by.loc[e.from_source_record_id,'root'])]=find(by.loc[e.to_source_record_id,'root'])
D['root']=D.root.map(find)
P=pd.concat([P.reset_index(),P1]).drop_duplicates('target_source_record_id',keep='last').set_index('target_source_record_id')
# Printed station versus settlement designators retain the same physical object level.
def compat(a,b):return a==b or set([a,b])=={'поселок','станция'}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def name(x):
 x=str(x).lower().replace('ё','е');x=re.sub(r'^(при станции|железнодорожная станция|станции|станция|поселок)\s+','',x);return re.sub(r'[^а-я0-9]+',' ',x).strip()
D['key']=D.name_norm.map(name);by=D.set_index('source_record_id',drop=False)
roots={k:g for k,g in D.groupby('root')};files={k:g.sort_values('ord') for k,g in D.groupby('source_file')}
edges=[];points=[];witness=[];dis=[];seen=set()
def bracket(t,c):
 g=files[t.source_file];pre=g[(g.ord<t.ord)&(g.ord>=t.ord-40)].sort_values('ord',ascending=False);post=g[(g.ord>t.ord)&(g.ord<=t.ord+40)].sort_values('ord')
 def anchor(a):
  for x in a.itertuples():
   gg=roots[x.root];gg=gg[(gg.census_year==c.census_year)&(gg.source_file==c.source_file)]
   if len(gg)==1:return x,gg.iloc[0]
  return None
 a=anchor(pre);b=anchor(post)
 if not a or not b:return None
 if a[1].ord<c.ord<b[1].ord and b[1].ord-a[1].ord<=40 and b[0].ord-a[0].ord<=40:
  return {'left_target_anchor':a[0].source_record_id,'left_candidate_anchor':a[1].source_record_id,'right_target_anchor':b[0].source_record_id,'right_candidate_anchor':b[1].source_record_id}
 return None
for rr in R.itertuples():
 t=by.loc[rr.source_record_id];group=roots[t.root];matches=[];proof=[]
 typed=bool(re.search(r'часть|^и станция',t.name_norm))
 if not typed:
  cand=D[(D.region_norm==t.region_norm)&(D.key==t.key)&(D.census_year!=t.census_year)]
  for year,cg in cand.groupby('census_year'):
   # Existing components cannot acquire a second member for an already observed year.
   if year in set(group.census_year):continue
   cc=cg[(cg.county==t.county)&(cg.county!='')]
   chosen=None;basis=None
   if len(cc)==1 and compat(cc.type_norm.iloc[0],t.type_norm):
    chosen=cc.iloc[0];basis={'rule':'unique_exact_own_name_type_and_native_county','target_county_basis':t.county_basis,'candidate_county_basis':chosen.county_basis}
   else:
    bp=[]
    for c in cg.itertuples():
     if not compat(c.type_norm,t.type_norm):continue
     if t.county and c.county and t.county!=c.county:continue
     b=bracket(t,c)
     if b:bp.append((c,b))
    if len(bp)==1:chosen=by.loc[bp[0][0].source_record_id];basis={'rule':'two_sided_existing_accepted_native_source_order_anchors_unique_own_name_type',**bp[0][1]}
   if chosen is not None:
    cg2=roots[chosen.root]
    if set(cg2.census_year)&set(group.census_year):continue
    matches.append(chosen);proof.append(basis)
  # Joint uniqueness must remain one record per year after all merges.
  allmembers=pd.concat([group]+[roots[m.root]for m in matches]).drop_duplicates('source_record_id')
  if allmembers.census_year.duplicated().any():matches=[];proof=[];allmembers=group
 else:allmembers=group
 donors=[P.loc[s] for s in allmembers.source_record_id if s in P.index]
 coherent=True
 if donors:
  lat=float(donors[0].latitude);lon=float(donors[0].longitude)
  for p in donors:
   dist=6371*2*math.asin(min(1,math.sqrt(math.sin(math.radians(float(p.latitude)-lat)/2)**2+math.cos(math.radians(lat))*math.cos(math.radians(float(p.latitude)))*math.sin(math.radians(float(p.longitude)-lon)/2)**2)))
   if dist>5:coherent=False
 if not coherent:matches=[];proof=[];allmembers=group;donors=[P.loc[s]for s in group.source_record_id if s in P.index]
 for m,b in zip(matches,proof):
  pair=tuple(sorted([t.source_record_id,m.source_record_id]))
  if pair not in seen:
   seen.add(pair);wid=len(witness);witness.append({'target':t.source_record_id,'candidate':m.source_record_id,'target_name':t.settlement_name,'candidate_name':m.settlement_name,'target_type':t.type_norm,'candidate_type':m.type_norm,'target_county':t.county,'candidate_county':m.county,'proof':b,'all_same_name_region_competitors':D[(D.region_norm==t.region_norm)&(D.key==t.key)].source_record_id.tolist()})
   edges.append(dict(from_source_record_id=t.source_record_id,to_source_record_id=m.source_record_id,relation='same_place',decision_status='checked_rule_accepted',admission_method=b['rule'],admission_rule=json.dumps(b,ensure_ascii=False),population_boundary_comparability_asserted=False,evidence_file=str(O/'identity_witnesses.json'),evidence_locator=f'[{wid}]'))
 if not typed and coherent and donors:
  p=next((P.loc[s] for s in allmembers[allmembers.census_year.eq(2021)].source_record_id if s in P.index),donors[0])
  for s in allmembers.source_record_id:
   if s in P.index:continue
   points.append(dict(target_source_record_id=s,latitude=p.latitude,longitude=p.longitude,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=p.coordinate_source_record_id,point_origin_file=p.point_origin_file,point_origin_sha256=p.point_origin_sha256,point_origin_locator=p.point_origin_locator,point_origin_kind=p.point_origin_kind,coordinate_binding_rule='accepted_component_plus_checked_native_county_or_two_sided_source_order_identity',point_use_inference='Retrospective representative own-locality point continuity inference; no census-date measurement claim.',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,external_provider_ID_binding_asserted=False,current_carrier_source_record_id=p.name))
 dis.append(dict(source_record_id=t.source_record_id,settlement_name=t.settlement_name,region_norm=t.region_norm,census_year=t.census_year,baseline_has_ownpoint=rr.has_ownpoint,baseline_has_admitted_route=rr.has_admitted_route,added_edge_count=len(matches),result_years=','.join(map(str,sorted(set(allmembers.census_year)))),point_available=bool(donors),disposition='typed_part_or_combined_row_requires_separate_scope_evidence'if typed else 'accepted_native_continuity_and_existing_own_point'if matches and donors and coherent else 'accepted_existing_component_point_transfer'if not rr.has_ownpoint and donors and coherent else 'unresolved_no_unique_source_bound_temporal_partner'if not matches else 'accepted_native_temporal_partner_point_still_unresolved'))
edgecols=['from_source_record_id','to_source_record_id','relation','decision_status','admission_method','admission_rule','population_boundary_comparability_asserted','evidence_file','evidence_locator'];pointcols=['target_source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_binding_rule','point_use_inference','historical_census_coordinate_asserted','population_boundary_comparability_asserted','external_provider_ID_binding_asserted','current_carrier_source_record_id']
pd.DataFrame(edges,columns=edgecols).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points,columns=pointcols).drop_duplicates('target_source_record_id').to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(dis).to_csv(O/'record_dispositions.csv',index=False);(O/'identity_witnesses.json').write_text(json.dumps(witness,ensure_ascii=False,indent=2));print(len(edges),len(points));print(pd.DataFrame(dis).disposition.value_counts().to_string())
