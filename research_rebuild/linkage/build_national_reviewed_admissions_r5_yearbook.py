"""Apply the independently reviewed ordinary 2010↔2021 Yearbook 4.9 bridge.
Four pairs already connected in R4 are recorded as supporting decisions, not edges.
No coordinate, scope-equivalence or population harmonization claim is added.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re, shutil
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'research_rebuild/evidence'
BASE=E/'releases/national_reviewed_admissions_r4_metadata_20260930'
SOURCE=E/'releases/national_source_selection_r1_20260930'
CAND=E/'discovery/yearbook_table49_2010_2021_candidates_r2_20260930/bridge_candidates_2010_2021.csv'
CAND_MAN=E/'discovery/yearbook_table49_2010_2021_candidates_r2_20260930/manifest.json'
REVIEW=E/'reviews/rosstat_yearbook_2024_table4_9_review_r2_20260930'
REVIEW_JSON=REVIEW/'review.json'; REVIEW_MAN=REVIEW/'manifest.json'
YEARBOOK=E/'discovery/official_sources_2010_2021_r2_yearbook/raw/rosstat_russian_statistical_yearbook_2024.pdf'
RECEIPT=E/'discovery/official_sources_2010_2021_r2_yearbook/retrieval_receipt.json'
OUT_ID='national_reviewed_admissions_r5b_yearbook_20260930'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def n(v):
 s='' if pd.isna(v) else str(v)
 s=s.casefold().replace('ё','е').replace('ѐ','е')
 s=re.sub(r'[«»\"\'`()\[\]{}.,;:№/\\–—-]',' ',s)
 return re.sub(r'\s+',' ',s).strip()
def region_key(v):
 words=[w for w in n(v).split() if w not in {'республика','область','край','автономная','автономный','округ','ао','респ','обл','кр','имени','город','федерального','значения'}]
 key=' '.join(words)
 return {'северная осетия алания':'северная осетия','саха якутия':'саха','ханты мансийский югра':'ханты мансийский'}.get(key,key)
def build(out:Path):
 out=out.resolve()
 if out.exists():raise FileExistsError(out)
 out.mkdir(parents=True)
 pins={BASE/'release_manifest.json':'93801f54ae9e56838a79b614494e0bfdd5b8c09b9585231bd634c13689d4d92e',
  SOURCE/'release_manifest.json':'37b4bf695087032e13baac88e7c432849bf3aa4543e40bcd2a5df6e8429242f6',
  SOURCE/'selected_observations.parquet':'dd8d437c1a1f5cebf2b45c55e7a6e2015f3c1a295cade827a71bb76189a485df',
  CAND:'c158e203a8600010acb5a2feef82e7cc158633145924a3ceba1cc91e1cc23ac4',
  CAND_MAN:'c02e2dd0b596c8e22a3c4441fbcbcd2e65e2405dfed5ee930f9e49f2ec72592b',
  REVIEW_JSON:'8996b7bd4eceec1df6fd5cfc40f2addcbf06887721545c2d68bad5181d63351a',
  REVIEW_MAN:'9bdc8f9055896514a53955e55784157c277bec79a1d71e578675a9bf05343c60',
  YEARBOOK:'bac43b438869d7b11ca595acd121726833d2bf2e54004351db825cade4c29da7',
  RECEIPT:'6aeb580c4b9ed3ab70a8abd46f7cf49e554b102139a42684299d669fe971773d'}
 # Review manifest hash is validated independently from the parent release manifest.
 for p,h in pins.items():
  if not p.is_file():raise FileNotFoundError(f'required input missing: {p}')
  actual=sha(p)
  if actual!=h:raise ValueError(f'pinned input mismatch {p}: {actual}')
 review_manifest=json.loads(REVIEW_MAN.read_text())
 if sha(REVIEW_MAN)[:8]!='9bdc8f90':raise ValueError('Yearbook review manifest changed')
 if review_manifest.get('status')!='PASS_RULE_FAMILY_WITH_HELD_EXCEPTIONS':raise ValueError('Yearbook review gate has not passed')
 review=json.loads(REVIEW_JSON.read_text())
 if review['rule_population']['candidate_pairs']!=163 or review['sample']['result'][:5]!='24/24':raise ValueError('review does not authorize exactly 163-pair rule family')
 base_manifest=json.loads((BASE/'release_manifest.json').read_text())
 for name,entry in base_manifest.get('outputs',{}).items():
  f=BASE/name
  if f.is_file() and entry.get('sha256') and sha(f)!=entry['sha256']:raise ValueError(f'parent release corruption: {f}')
 selected=pd.read_parquet(SOURCE/'selected_observations.parquet')
 if selected.source_record_id.astype(str).duplicated().any():raise ValueError('selected source_record_id duplicated')
 selected=selected.copy();selected['source_record_id']=selected.source_record_id.astype(str)
 idx=selected.set_index('source_record_id',drop=False)
 cand=pd.read_csv(CAND)
 cand=cand[cand.candidate_status_2010_2021.eq('candidate_for_independent_review')].copy()
 if len(cand)!=163 or cand['2010_source_record_id'].duplicated().any() or cand['2021_source_record_id'].duplicated().any():raise ValueError('candidate endpoint uniqueness/count failed')
 old_edges=pd.read_csv(BASE/'identity_edges_accepted.csv')
 edges=[]
 for r in old_edges.itertuples(index=False):edges.append((str(r.from_source_record_id),str(r.to_source_record_id)))
 parent={}
 def find(a):
  parent.setdefault(a,a)
  if parent[a]!=a:parent[a]=find(parent[a])
  return parent[a]
 def union(a,b):
  ra,rb=find(a),find(b)
  if ra==rb:return False
  parent[rb]=ra;return True
 for a,b in edges:union(a,b)
 decisions=[];new_edges=[];new_mass={2010:0,2021:0};new_ids={2010:set(),2021:set()};already=[]
 for _,r in cand.iterrows():
  sid10=str(r['2010_source_record_id']);sid21=str(r['2021_source_record_id'])
  if sid10 not in idx.index or sid21 not in idx.index:raise ValueError(f'candidate endpoint not selected: {sid10} {sid21}')
  a=idx.loc[sid10];b=idx.loc[sid21]
  if int(a.census_year)!=2010 or int(b.census_year)!=2021:raise ValueError('candidate years do not match source IDs')
  if n(a.settlement_name)!=n(b.settlement_name) or n(a.settlement_name)!=n(r['normalized_city_label']):raise ValueError(f'name binding mismatch {sid10}/{sid21}')
  if n(a.settlement_type)!=n(b.settlement_type) or n(a.settlement_type)!=n(r['2010_settlement_type']):raise ValueError(f'type binding mismatch {sid10}/{sid21}')
  if region_key(a.region_raw)!=region_key(b.region_raw) or region_key(a.region_raw)!=region_key(r['2010_region_raw']) or region_key(a.region_raw)!=region_key(r['2021_region_raw']):raise ValueError(f'region binding mismatch {sid10}/{sid21}')
  p10=int(a.population);p21=int(b.population)
  if p10!=int(r['2010_population']) or p21!=int(r['2021_population']):raise ValueError('candidate population is not the selected source value')
  if not bool(r['2010_rounding_compatible']) or not bool(r['2021_rounding_compatible']):raise ValueError('candidate rounding compatibility failed')
  if pd.notna(r['footnote_markers']) and str(r['footnote_markers']).strip():raise ValueError('footnoted case entered ordinary rule')
  if find(sid10)==find(sid21):
   action='recorded_supporting_evidence_no_duplicate_edge';already.append((sid10,sid21))
  else:
   action='applied';union(sid10,sid21)
   new_edges.append({'decision_id':f"YB49-BRIDGE-{hashlib.sha256((sid10+'|'+sid21).encode()).hexdigest()[:24]}",'relation':'same_place','from_source_record_id':sid10,'from_year':2010,'to_source_record_id':sid21,'to_year':2021,'decision_class':'rule','decision_status':'accepted_rule_family_after_independent_sample_review','decision_rule':'official_yearbook_table4_9_exact_selected_endpoint_binding_v1','reviewer':'independent_24_case_stratified_rule_review_plus_deterministic_endpoint_binding','reviewed_at':'2026-09-30','evidence_uri':str(r['row_id']),'evidence_sha256':sha(YEARBOOK),'endpoint_publication_binding_from':None,'endpoint_publication_binding_to':None,'population_scope_interpretation':'same-city continuity only; source publishes year-specific census-date populations in respective-year boundaries; no boundary harmonization, coordinate or equal-scope claim'})
   new_mass[2010]+=p10;new_mass[2021]+=p21;new_ids[2010].add(sid10);new_ids[2021].add(sid21)
  did=f"YB49-DECISION-{hashlib.sha256((sid10+'|'+sid21).encode()).hexdigest()[:24]}"
  decisions.append({'decision_id':did,'relation':'same_place','from_source_record_id':sid10,'from_year':2010,'to_source_record_id':sid21,'to_year':2021,'decision_action':action,'decision_status':'accepted_rule_family_after_independent_sample_review','decision_class':'rule','decision_rule':'official_yearbook_table4_9_exact_selected_endpoint_binding_v1','reviewer':'independent_24_case_stratified_rule_review_plus_deterministic_endpoint_binding','evidence_row_id':str(r['row_id']),'evidence_pdf_page_1based':int(r['pdf_page_1based']),'evidence_printed_page':int(r['printed_page']),'evidence_raw_label':str(r['raw_russian_label']),'evidence_raw_table_line':str(r['raw_table_line']),'evidence_source_pdf_sha256':sha(YEARBOOK),'selected_2010_population':p10,'selected_2021_population':p21,'yearbook_2010_thousand_raw':str(r['2010_raw']),'yearbook_2021_thousand_raw':str(r['2021_raw']),'yearbook_rounding_compatibility_is_operational_check_only':True,'identity_scope':'direct published same-city continuity; no population or geographic harmonization'})
 if len(decisions)!=163 or len(new_edges)!=159 or len(already)!=4:raise ValueError(f'unexpected partition decisions={len(decisions)} edges={len(new_edges)} already={len(already)}')
 if len({r['decision_id'] for r in new_edges})!=len(new_edges):raise ValueError('new decision ID collision')
 all_edges=pd.concat([old_edges,pd.DataFrame(new_edges)],ignore_index=True)
 if all_edges.decision_id.duplicated().any():raise ValueError('accepted edge decision IDs collide')
 # Validate every selected vertex occurring in the graph has at most one observation per census year.
 linked=set(all_edges.from_source_record_id.astype(str))|set(all_edges.to_source_record_id.astype(str))
 graph_nodes=selected[selected.source_record_id.isin(linked)]
 graph_nodes=graph_nodes.assign(component=graph_nodes.source_record_id.map(find))
 dup=graph_nodes.groupby(['component','census_year']).source_record_id.nunique()
 if (dup>1).any():raise ValueError('a resulting same-place component contains multiple selected observations in one census year')
 # Compute lower-bound identity coverage over the selected source observations.
 coverage=[]
 for year in (2002,2010,2021):
  sub=graph_nodes[graph_nodes.census_year.eq(year)]
  den=selected[selected.census_year.eq(year)]
  pop=int(sub.population.sum())
  total=int(den.population.sum())
  coverage.append({'year':year,'selected_rows_denominator':len(den),'selected_population_denominator':total,'identity_linked_unique_rows':len(sub),'identity_linked_unique_population':pop,'identity_row_share_percent':round(100*len(sub)/len(den),6),'identity_population_share_percent':round(100*pop/total,6),'interpretation':'certified lower bound among selected observations connected by accepted same_place edges; no extrapolation; yearbook bridge does not establish equal boundaries/population scope or coordinates'})
 # R5 inherits non-identity artifacts exactly; coordinate data remain untouched.
 for filename in ['coordinate_admissions.csv','reviewed_case_axes.csv','publication_bindings.csv','tom11_bridge_decisions.csv']:
  shutil.copy2(BASE/filename,out/filename)
 all_edges.to_csv(out/'identity_edges_accepted.csv',index=False)
 pd.DataFrame(decisions).to_csv(out/'yearbook_bridge_decisions.csv',index=False)
 pd.DataFrame(new_edges).to_csv(out/'yearbook_new_identity_edges.csv',index=False)
 pd.DataFrame(coverage).to_csv(out/'coverage_by_year.csv',index=False)
 selected_rows=cand[['row_id','2010_source_record_id','2021_source_record_id','normalized_city_label','2010_settlement_type','2010_region_raw','2021_region_raw','2010_population','2021_population','2010_raw','2021_raw','pdf_page_1based','printed_page','raw_russian_label','raw_table_line','2010_source_sha256','2021_source_sha256']].copy()
 selected_rows['decision_action']=[d['decision_action'] for d in decisions]
 selected_rows.to_csv(out/'accepted_and_deduplicated_yearbook_pairs.csv',index=False)
 base_linked=set(old_edges.from_source_record_id.astype(str))|set(old_edges.to_source_record_id.astype(str))
 incremental=[]
 for year in (2002,2010,2021):
  newly=graph_nodes[(graph_nodes.census_year.eq(year))&(~graph_nodes.source_record_id.isin(base_linked))]
  incremental.append({'year':year,'newly_linked_selected_rows':len(newly),'newly_linked_selected_population':int(newly.population.sum())})
 inputs={str(p.relative_to(ROOT)):sha(p) for p in list(pins.keys())}
 manifest={'release_id':OUT_ID,'parent_release_id':'national_reviewed_admissions_r4_metadata_20260930','status':'reviewed_identity_admission_release','scope':'163 ordinary unique official Yearbook 4.9 city rows linking selected 2010 and 2021 observations; coordinates and scope unchanged','verified_inputs':inputs,'review_gate':{'review_manifest':str(REVIEW_MAN.relative_to(ROOT)),'review_manifest_sha256':sha(REVIEW_MAN),'review_sha256':sha(REVIEW_JSON),'n_fixed_stratified':24,'accepted':24,'candidate_pairs':163,'held_exceptions':9,'rounding_rule_note':'nearest-thousand ±500 is an operational compatibility check only; source rounding convention is not asserted'},'decisions':{'candidate_pairs':163,'already_connected_supporting_decisions':len(already),'new_identity_edges':len(new_edges),'newly_linked_coverage_by_year':incremental,'new_edge_endpoint_population_mass_2010':new_mass[2010],'new_edge_endpoint_population_mass_2021':new_mass[2021],'whole_eligible_endpoint_mass_2010':int(cand['2010_population'].sum()),'whole_eligible_endpoint_mass_2021':int(cand['2021_population'].sum())},'identity_component_invariant':'all components contain at most one selected source observation per census year','coordinate_invariant':'parent coordinate admissions copied byte-for-byte; no new point or historical coordinate admissions','population_scope':'source values retained by year; this bridge asserts same-place identity, not equal population scope or boundary harmonization','limitations':['The 163 rows are a rule-defined high-population candidate family, not a probability sample of all settlements.','The 24/24 fixed validation is not a national precision estimate.','Four candidates were already connected in R4 and are recorded as supporting decisions without duplicate graph edges.','Nine Yearbook exceptions remain held outside this release.','No coordinate or point-in-time geometry is admitted by Yearbook continuity.'],'builder_sha256':sha(Path(__file__).resolve()),'outputs':{}}
 for f in sorted(out.iterdir()):
  rows=None
  if f.suffix=='.csv':
   with f.open(encoding='utf-8',newline='') as stream:rows=max(0,sum(1 for _ in csv.reader(stream))-1)
  manifest['outputs'][f.name]={'sha256':sha(f),'bytes':f.stat().st_size,'rows':rows}
 (out/'release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
 return manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
