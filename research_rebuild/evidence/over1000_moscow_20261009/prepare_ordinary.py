from pathlib import Path
import pandas as pd,json,hashlib,xlrd,re,math
O=Path(__file__).parent;d=pd.read_csv(O/'native_all_with_independent_county.csv.gz');a=pd.read_csv(O/'assigned79_native_UIDs.csv');p=pd.read_csv(O/'moscow_ownpoint_snapshot68.csv.gz').drop_duplicates('target_source_record_id',keep='last').set_index('target_source_record_id');g=d.groupby('root');edges=[];points=[];proof=[];rivals=[];hold=[];seen=set();sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
raw2=Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls');raw10=Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls');sheets={2002:xlrd.open_workbook(str(raw2)).sheet_by_index(0),2010:xlrd.open_workbook(str(raw10)).sheet_by_name('Data Sheet')};t=pd.read_csv(O/'native2010_independent_county_anchor_inventory.csv.gz');anchors=t[t.anchor_county.notna()].sort_values('rowno');raws=[]
for r in a.itertuples():
 x=d[d.source_record_id.eq(r.source_record_id)].iloc[0]
 if pd.isna(x.derived_oldcounty):continue
 cand=d[d.name_norm.eq(x.name_norm)&d.type_norm.eq(x.type_norm)&d.derived_oldcounty.eq(x.derived_oldcounty)].copy()
 rivals.extend(cand.assign(target_UID=r.source_record_id).to_dict('records'))
 if cand.census_year.duplicated().any()or set(cand.census_year)!={2002,2010,2021}:continue
 roots=set(cand.root)
 if len(roots)==1 or tuple(sorted(roots))in seen:continue
 seen.add(tuple(sorted(roots)));full=pd.concat([g.get_group(z)for z in roots]);
 if full.census_year.duplicated().any():hold.append(dict(case=x.settlement_name,reason='Existing component has competing same-year native record; do not rewire',UIDs='|'.join(cand.source_record_id)));continue
 cur=cand[cand.census_year.eq(2021)].iloc[0]
 if cur.source_record_id not in p.index:continue
 cr=p.loc[cur.source_record_id];case='moscow_exact_native_county_'+str(cur.source_record_id.rsplit(':',1)[1])
 for z in cand.itertuples():
  if z.census_year in [2002,2010]:
   n=int(z.source_record_id.rsplit(':',1)[1]);vals=sheets[z.census_year].row_values(n-1);rf=raw2 if z.census_year==2002 else raw10;assert any(str(v).replace(".0","")==str(int(z.population))for v in vals), (case,z.census_year,vals);raws.append(dict(case=case,source_record_id=z.source_record_id,source_path=str(rf),source_sha256=sha(rf),source_locator=f'{sheets[z.census_year].name}:row{n}',raw_cells_json=json.dumps(vals[:8],ensure_ascii=False),native_population=z.population,original_district_raw=z.district_raw,derived_sourcecounty=z.derived_oldcounty,imported_district_not_mutated=True))
  if z.census_year==2010:
   n=int(z.source_record_id.rsplit(':',1)[1]);lo=anchors[anchors.rowno<n].iloc[-1];hi=anchors[anchors.rowno>n].iloc[0];assert lo.anchor_county==hi.anchor_county==z.derived_oldcounty
   for ar in [lo,hi]:proof.append(dict(case=case,target_UID=z.source_record_id,anchor_UID=ar.source_record_id,anchor_original_2002_county=ar.anchor_county,anchor_root=ar.root,anchor_three_census_already_accepted=True,raw_source_path=str(raw10),raw_source_sha256=sha(raw10),raw_source_locator=f'Data Sheet:row{ar.rowno}',literal_raw_cells_json=json.dumps(sheets[2010].row_values(ar.rowno-1)[:8],ensure_ascii=False)))
  if z.root!=cur.root:edges.append(dict(from_source_record_id=z.source_record_id,to_source_record_id=cur.source_record_id,relation='same_place',decision_status='checked_rule_accepted',case=case,admission_rule='Exact original own native name+type, unique within independently source-bracketed original county; current own code point; all three distinct actual source-year rows; all same-county rivals retained',source_binding_proof='native_raw_row_witnesses.csv.gz;independent_source_county_anchors.csv.gz;all_native_identity_rivals.csv.gz',population_boundary_comparability_asserted=False,municipal_event_date='UNKNOWN'))
  if z.source_record_id not in p.index:points.append(dict(target_source_record_id=z.source_record_id,latitude=cr.latitude,longitude=cr.longitude,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_source_record_id=cur.source_record_id,source_sha256=cr.point_origin_sha256,source_locator=cr.point_origin_locator,point_origin_file=cr.point_origin_file,point_origin_sha256=cr.point_origin_sha256,point_origin_locator=cr.point_origin_locator,point_origin_kind=cr.point_origin_kind,case=case,coordinate_binding_rule='Unique ordinary native locality identity via literal name/type and independently anchored county; own admitted current point retained with original provider provenance',point_use_inference='own_modern_representative_point_on_source_bound_native_identity',population_boundary_comparability_asserted=False,historical_census_coordinate_asserted=False,secondary_population_not_substituted_for_native=True))
for name,rows in [('accepted_identity_edge_delta.csv',edges),('accepted_point_use_delta.csv',points),('native_raw_row_witnesses.csv.gz',raws),('independent_source_county_anchors.csv.gz',proof),('all_native_identity_rivals.csv.gz',rivals),('ordinary_component_collision_holds.csv',hold)]:pd.DataFrame(rows).to_csv(O/name,index=False)
print('edges',len(edges),'points',len(points),'cases',len(set(x['case']for x in edges)));print(pd.DataFrame(edges)[['case','from_source_record_id']].to_string(index=False))
