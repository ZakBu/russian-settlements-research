#!/usr/bin/env python3
import csv, hashlib, json
from pathlib import Path
from collections import defaultdict
import duckdb
OUT=Path('/tmp/graph29_2010_top30_audit_20261005')
SEL='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
RES='/workspace/settlements-work/continuation_20261004/accepted_graph24_anapa_20261005/scoped_joint_residual.parquet'
EDGE='/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet'
POINT='/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet'
QUAL='/tmp/graph29_ozherele_points_20261005/qualifying_residual_rows.csv'
OLD='/workspace/settlements-work/continuation_20261004/regions/top15_2010_residual_graph24_cached_evidence_audit_v1/top15_dispositions.csv'
IDENT='/workspace/settlements-delivery/continuation-consolidated-20261003/identifier_snapshot_claims_candidates.parquet'
WIKI='/workspace/settlements-delivery/continuation-consolidated-20261003/wiki_literal_associations.parquet'
EVID='/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet'
con=duckdb.connect()
selected=con.execute(f"select source_record_id,census_year,settlement_name,settlement_type,region_raw,region_norm,district_raw,municipality_raw,population,population_value_quality,source_file,source_sheet,source_row,source_native_id,source_sha256,source_locator,okato,oktmo,settlement_id from read_parquet('{SEL}')").df()
res=con.execute(f"select * from read_parquet('{RES}') where census_year=2010").df()
# accepted same-place components from current Graph28 identity ledger
parent={}
def find(x):
 p=parent.setdefault(x,x)
 if p!=x: parent[x]=find(p)
 return parent[x]
def union(a,b):
 a=find(a); b=find(b)
 if a!=b: parent[b]=a
accepted_edge_statuses=['accepted_case_specific','accepted_rule_family_after_independent_sample_review','case_review_accepted','case_specific_independent_review_accepted','checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect','independent_case_review_accepted']
for a,b in con.execute(f"select from_source_record_id,to_source_record_id from read_parquet('{EDGE}') where relation='same_place' and decision_status in ({','.join(repr(x) for x in accepted_edge_statuses)})").fetchall(): union(a,b)
cy=defaultdict(set)
for r in selected.itertuples(): cy[find(r.source_record_id)].add(int(r.census_year))
accepted_point_statuses=['frozen_r5b_reviewed_baseline_preserved','reviewed_case_accepted','reviewed_extension_rule_accepted','reviewed_rule_accepted']
pts=con.execute(f"select distinct target_source_record_id from read_parquet('{POINT}') where coordinate_admission_status in ({','.join(repr(x) for x in accepted_point_statuses)})").fetchall()
pointids={r[0] for r in pts}
res=res.merge(selected,on=['source_record_id','census_year'],suffixes=('_res','_sel'))
res['component_years']=res.source_record_id.map(lambda x: sorted(cy[find(x)]))
res['component_year_count']=res.component_years.map(len)
res['has_accepted_point']=res.source_record_id.isin(pointids)
res['current_metric_covered']=res.has_accepted_point & (res.component_year_count>=2)
res['metric_reason']=res.apply(lambda r: 'covered: accepted point + component years '+','.join(map(str,r.component_years)) if r.current_metric_covered else ('missing accepted point; component years '+','.join(map(str,r.component_years)) if not r.has_accepted_point else 'point accepted; only '+','.join(map(str,r.component_years))+' actual component year(s)'),axis=1)
# independent result check against Graph29 row ledger
qual=set(con.execute(f"select source_record_id from read_csv_auto('{QUAL}') where census_year=2010").fetchnumpy()['source_record_id'])
calc=set(res.loc[res.current_metric_covered,'source_record_id'])
if qual != calc:
 print('QUAL_DIFF calculated-only',len(calc-qual),'file-only',len(qual-calc))
old=list(csv.DictReader(open(OLD,encoding='utf-8')))
oldids={r['source_record_id_2010'] for r in old}
overlap=res[res.source_record_id.isin(oldids)].copy()
ranked=res[~res.source_record_id.isin(oldids)].sort_values(['population_sel','source_record_id'],ascending=[False,True]).head(30).copy()
ranked.insert(0,'rank_after_excluding_prior15',range(1,len(ranked)+1))
# Source record IDs in old audit that did not occur in current residual are separately noted.
not_present=sorted(oldids-set(res.source_record_id))
# Exact selected records by name+region, no fuzzy; preserve all actual exact candidates.
all_sel=selected
for y in [2002,2021]:
 cand=[]
 for row in ranked.itertuples():
  matches=all_sel[(all_sel.census_year==y)&(all_sel.settlement_name.fillna('').str.casefold()==str(row.settlement_name_sel).casefold())&(all_sel.region_norm.fillna('').str.casefold()==str(row.region_norm_sel).casefold())]
  vals=[]
  for m in matches.itertuples():
   vals.append({'id':m.source_record_id,'name':m.settlement_name,'type':m.settlement_type,'region':m.region_raw,'region_norm':m.region_norm,'pop':m.population,'quality':m.population_value_quality,'district':m.district_raw,'municipality':m.municipality_raw,'okato':m.okato,'oktmo':m.oktmo,'locator':f'{m.source_file}:{m.source_sheet}:{m.source_row}'})
  cand.append(vals)
 ranked[f'exact_{y}_same_name_region']=cand
# 2010->2021 legacy source-evidence routes, only literal name and region matching surfaced as candidate.
ranked['legacy_source_evidence_route']=None
for idx,row in ranked.iterrows():
 rid=row['source_record_id']; nm=str(row['settlement_name_sel'])
 ev=con.execute(f"select source_evidence_json from read_parquet('{EVID}') where source_record_id=? and census_year=2010",[rid]).fetchone()
 route={}
 if ev:
  d=json.loads(ev[0])
  for k in ['legacy_identity_status','legacy_identity_reasons','legacy_match_method','legacy_matched_to_source_record_id','legacy_verified_successor_settlement_id','legacy_identity_conflict','legacy_population','legacy_quality_flag']:
   route[k]=d.get(k)
 ranked.at[idx,'legacy_source_evidence_route']=route
# exact-name exact-region 2009/historic identifier claims; no binding admission implied
ranked['exact_name_code_claims']=None
ranked['exact_name_wikidata_routes']=None
for idx,row in ranked.iterrows():
 nm=str(row['settlement_name_sel']); reg=str(row['region_raw'])
 # Exact names only; broad output capped, match-region explained via raw fields and not interpreted as row binding.
 cs=con.execute(f"select distinct identifier_system,raw_code,normalized_exact_code,type_raw,region_raw,binding_status,source_snapshot_version,source_locator from read_parquet('{IDENT}') where lower(trim(name_raw))=lower(?) limit 30",[nm]).fetchall()
 ranked.at[idx,'exact_name_code_claims']=[dict(identifier_system=z[0],raw_code=z[1],normalized_exact_code=z[2],type=z[3],region=z[4],binding_status=z[5],snapshot=z[6],locator=z[7]) for z in cs]
 # local wikidata literal associations; require exact name only; preserve region, status to avoid homonym inference
 qs=con.execute(f"select distinct wikidata_qid,current_source_name,current_source_type,current_source_region,assertion_link_status,physical_site_continuity_status,place_identity_admission,source_locator_original_reviewed from read_parquet('{WIKI}') where lower(trim(current_source_name))=lower(?) limit 30",[nm]).fetchall()
 ranked.at[idx,'exact_name_wikidata_routes']=[dict(qid=z[0],name=z[1],type=z[2],region=z[3],link_status=z[4],continuity=z[5],identity=z[6],locator=z[7]) for z in qs]
# csv serializes JSON columns
out=OUT/'top30_2010_after_excluding_prior15.csv'
ranked.to_csv(out,index=False,quoting=csv.QUOTE_MINIMAL)
overlap.to_csv(OUT/'prior15_overlap_current_residual.csv',index=False)
# Population mass / quality by group
qualrows=res[res.current_metric_covered]
notrows=res[~res.current_metric_covered]
summary={
 'rank_scope':'2010 rows in current scoped residual, exact source_record_id overlap with prior 15 audit removed before ranking',
 'residual_2010_rows':int(len(res)), 'residual_2010_population_sum':float(res.population_sel.sum()),
 'current_metric_covered_rows_in_residual':int(len(qualrows)), 'current_metric_covered_population_in_residual':float(qualrows.population_sel.sum()),
 'currently_uncovered_rows_in_residual':int(len(notrows)), 'currently_uncovered_population_in_residual':float(notrows.population_sel.sum()),
 'prior15_source_ids':len(oldids),'prior15_ids_present_in_current_residual':len(overlap),'prior15_names_excluded':[r['settlement_name'] for r in old], 'prior15_absent_ids':not_present,
 'top30_population_sum':float(ranked.population_sel.sum()),'top30_covered_rows':int(ranked.current_metric_covered.sum()),'top30_covered_population_sum':float(ranked.loc[ranked.current_metric_covered,'population_sel'].sum()),'top30_uncovered_rows':int((~ranked.current_metric_covered).sum()),'top30_uncovered_population_sum':float(ranked.loc[~ranked.current_metric_covered,'population_sel'].sum()),
 'top30_quality_rows':ranked.groupby('population_value_quality_sel').agg(rows=('source_record_id','count'),population=('population_sel','sum')).reset_index().to_dict('records'),
 'top30_uncovered_quality_rows':ranked[~ranked.current_metric_covered].groupby('population_value_quality_sel').agg(rows=('source_record_id','count'),population=('population_sel','sum')).reset_index().to_dict('records'),
 'residual_quality_rows':res.groupby('population_value_quality_sel').agg(rows=('source_record_id','count'),population=('population_sel','sum')).reset_index().to_dict('records'),
 'uncovered_quality_rows':notrows.groupby('population_value_quality_sel').agg(rows=('source_record_id','count'),population=('population_sel','sum')).reset_index().to_dict('records'),
 'uncovered_reason_counts':notrows.groupby('metric_reason').agg(rows=('source_record_id','count'),population=('population_sel','sum')).reset_index().to_dict('records'),
 'top30_uncovered_reason_counts':ranked[~ranked.current_metric_covered].groupby('metric_reason').agg(rows=('source_record_id','count'),population=('population_sel','sum')).reset_index().to_dict('records'),
 'qualifier_match_to_graph29_csv':{'calculated_qualifying_ids':len(calc),'csv_qualifying_ids':len(qual),'calculated_only':len(calc-qual),'csv_only':len(qual-calc)},
 'systemic_risks':['2,564,779 of 2,921,527 residual 2010 population (87.8%) is confidentiality-protected secondary data with exact scope unverified; 1,867,820 of 2,141,667 currently uncovered population (87.2%) has the same limitation.','Common names and missing district context create collisions across 2002 and 2021 records; source-evidence routes marked quarantined are candidate traces, not admitted edges.','Historical OKATO/GeoKLADR and Wikidata name routes are not bound to the 2010 observation unless their source-record binding and dated event are established.'],
 'caveats':['Population totals are 2010 row values only; no multi-census summing or boundary comparability implied.','Population value quality is retained per row; secondary confidentiality-protected scope-unverified values remain secondary.','Exact name/region, classifier, and Wikidata routes are discovery candidates only, not identity admissions.']}
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
inputs=[SEL,RES,EDGE,POINT,QUAL,OLD,IDENT,WIKI,EVID]
manifest={'inputs':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in inputs},'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [out,OUT/'prior15_overlap_current_residual.csv',OUT/'summary.json']}}
(OUT/'sha256_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
print('OUTPUT',OUT)
