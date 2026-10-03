"""Apply reviewed exact-primary counts and migrate existing publication endpoints.

This replaces one selected census row with one independently matched publication
row. It preserves the old assertion, all identity decision evidence and point
origins. Publication equivalence adds no cross-year identity evidence.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from .coverage import identity_sets, sha
from .propagate_accepted_points import STATUS_OK

PRIMARY=Path('/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf')


def replace_selected(selected, proposals, approved_ids, primary_sha):
    if not selected.source_record_id.is_unique:
        raise ValueError('Selected IDs must be unique')
    if len(approved_ids)!=len(set(approved_ids)) or not approved_ids:
        raise ValueError('Nonempty unique approved primary ID list required')
    if not set(approved_ids).issubset(set(proposals.replacement_source_record_id)):
        raise ValueError('Approved replacement absent from candidate proposals')
    rows=proposals[proposals.replacement_source_record_id.isin(approved_ids)].copy()
    if not rows.stage_status.eq('proposed_pending_independent_review').all():
        raise ValueError('Review proposal status invalid')
    old_ids=rows.r2_source_record_id.tolist();new_ids=rows.replacement_source_record_id.tolist()
    if len(old_ids)!=len(set(old_ids)) or len(new_ids)!=len(set(new_ids)) or set(new_ids)&set(selected.source_record_id):
        raise ValueError('Publication binding not a one-to-one replacement')
    indexed=selected.set_index('source_record_id',drop=False)
    if not set(old_ids).issubset(indexed.index):raise ValueError('Displaced source ID not selected')
    if not indexed.loc[old_ids,'census_year'].eq(2010).all():raise ValueError('Publication replacement must remain within 2010')
    result=selected.copy();result['population_value_quality_original_tag']=selected.population_value_quality
    result['population_quality_limitation']=None
    protected=result.population_value_quality.eq('confidentiality_perturbed_within_ten')
    # Keep the legacy classification explicitly, while removing a now-refuted
    # universal precision interpretation from the current scientific quality.
    result.loc[protected,'population_value_quality']='secondary_confidentiality_protected_value_exact_scope_unverified'
    result.loc[protected,'population_quality_limitation']='Legacy within-ten tag retained separately; observed official-primary differences can exceed ten; protection and source-population scope effects not disentangled'
    result['displaced_source_record_id']=None
    result['publication_binding_basis']=None
    result['source_raw_line']=None
    row_index={rid:i for i,rid in zip(result.index,result.source_record_id)}
    bindings=[]
    for r in rows.itertuples(index=False):
        old=indexed.loc[r.r2_source_record_id]
        if float(old.population)!=float(r.old_population_r2) or old.population_value_quality!=r.old_population_quality:
            raise ValueError('Displaced population assertion differs from reviewed proposal')
        pop=int(r.proposed_primary_population)
        if pop<0 or pop!=float(r.proposed_primary_population):raise ValueError('Exact primary population must be nonnegative integral')
        if r.proposed_primary_men+r.proposed_primary_women!=pop:
            raise ValueError('Raw primary sexes do not sum to the total')
        if r.primary_source_sha256!=primary_sha or not r.primary_raw_direct_typed_locality_row:
            raise ValueError('Primary row hash or physical grain certificate differs')
        locator=json.dumps({'table':'5','pdf_page_1based':int(r.pdf_page),'printed_page':int(r.printed_page),
                            'text_line_start_1based':int(r.text_line_start_pypdf),'text_line_end_1based':int(r.text_line_end_pypdf),
                            'raw_label':r.table5_label_raw,'raw_district':r.primary_raw_district},ensure_ascii=False,sort_keys=True)
        values={'source_record_id':r.replacement_source_record_id,'population':pop,'source_population_raw':str(pop),
                'population_value_quality':'reviewed_primary_reported_value','population_quality_limitation':None,
                'source_name_raw':r.table5_label_raw,'source_file':'data/raw/2010_official_tom1/'+PRIMARY.name,
                'source_path':str(PRIMARY),'source_sha256':primary_sha,'source_locator':locator,
                'source_sheet':'pdf_page_'+str(int(r.pdf_page)),'source_row':int(r.text_line_start_pypdf),
                'source_native_id':r.replacement_source_record_id,'population_scope':'settlement',
                'men':r.proposed_primary_men,'women':r.proposed_primary_women,
                'source_raw_line':r.raw_pdf_line_independent_pypdf,
                'entity_grain_status':'atomic_physical_settlement_primary_table5_reviewed',
                'source_selection_component':'2010_official_table5_reviewed_publication_replacement',
                'district_raw':r.primary_raw_district,'displaced_source_record_id':r.r2_source_record_id,
                'publication_binding_basis':'reviewed_same_2010_physical_settlement_publication_binding_only',
                'latitude':None,'longitude':None,'oktmo':None,'okato':None,'fias_id':None,
                'coordinate_source':None,'coordinate_quality':None,'geocoder_settlement_name':None,
                'settlement_id':None,'linked_to_2021':False,
                'coverage_status':'limited_published_table5_coverage','snapshot_year':2010,
                'snapshot_rule_version':'reviewed_primary_table5_publication_replacement',
                'derivation_note':'Exact primary count replaces the displaced assertion via a reviewed same-census publication binding; accepted cross-year graph decisions are preserved separately.'}
        i=row_index[r.r2_source_record_id]
        for c,v in values.items():
            if c in result.columns:result.at[i,c]=v
        bindings.append({'old_source_record_id':r.r2_source_record_id,'new_source_record_id':r.replacement_source_record_id,
                         'census_year':2010,'old_population':float(old.population),'primary_population':pop,
                         'population_delta':pop-float(old.population),'binding_scope':'same-census publication only; no new cross-year identity evidence',
                         'primary_source_sha256':primary_sha,'primary_source_locator':locator})
    if not result.source_record_id.is_unique or len(result)!=len(selected):raise ValueError('Source replacement altered row multiplicity')
    expected=(set(selected.source_record_id)-set(old_ids))|set(new_ids)
    if set(result.source_record_id)!=expected:raise ValueError('Selected ID set differs from exact replacement mapping')
    unchanged=~selected.source_record_id.isin(old_ids)
    # These scientific observation fields must remain literal for every other
    # record. Only the explicit quality assessment of protected values changes.
    fields=['source_record_id','census_year','settlement_name','settlement_type','population','source_file','source_row','source_sheet','oktmo','okato']
    pd.testing.assert_frame_equal(result.loc[unchanged,fields],selected.loc[unchanged,fields],check_dtype=False)
    return result,pd.DataFrame(bindings)


def apply(selected_path,graph_path,points_path,evidence_path,proposals_path,review_path,output):
    if output.exists():raise FileExistsError('New immutable output required')
    paths={'selected':selected_path,'graph':graph_path,'points':points_path,'source_evidence':evidence_path,
           'proposals':proposals_path,'review':review_path,'primary_pdf':PRIMARY}
    pins={k:{'path':str(v),'sha256':sha(v)} for k,v in paths.items()}
    review=json.loads(review_path.read_text())
    if review.get('verdict')!='APPROVE_BOUNDED_PRIMARY_PUBLICATION_REPLACEMENTS':raise ValueError('Explicit independent primary publication approval required')
    for k in ['selected','proposals','primary_pdf']:
        if review.get(k+'_sha256')!=pins[k]['sha256']:raise ValueError('Review input hash differs: '+k)
    selected=pd.read_parquet(selected_path)
    proposals=pd.read_csv(proposals_path) if proposals_path.suffix=='.csv' else pd.read_parquet(proposals_path)
    result,bindings=replace_selected(selected,proposals,review.get('approved_replacement_source_record_ids',[]),pins['primary_pdf']['sha256'])
    mapping=dict(zip(bindings.old_source_record_id,bindings.new_source_record_id))
    graph=pd.read_parquet(graph_path);migrated=graph.copy()
    if not graph.decision_status.isin(STATUS_OK).all():raise ValueError('Graph contains unaccepted decisions')
    for c in ['from_source_record_id','to_source_record_id']:
        migrated[c]=graph[c].map(lambda rid:mapping.get(rid,rid))
    pd.testing.assert_frame_equal(migrated.drop(columns=['from_source_record_id','to_source_record_id']),graph.drop(columns=['from_source_record_id','to_source_record_id']))
    before=identity_sets(selected,graph);after=identity_sets(result,migrated)
    if len(before[0])!=len(after[0]) or len(before[1])!=len(after[1]) or len(before[2])!=len(after[2]):raise ValueError('Publication migration altered accepted connectivity')
    points=pd.read_parquet(points_path);point_migration=points.copy()
    point_migration['target_source_record_id']=points.target_source_record_id.map(lambda rid:mapping.get(rid,rid))
    structural=['inference_identity_path_from_source_record_id','inference_identity_path_to_source_record_id']
    for c in structural:
        if c in points:point_migration[c]=points[c].map(lambda rid:mapping.get(rid,rid))
    scientific=points.columns.difference(['target_source_record_id']+structural)
    pd.testing.assert_frame_equal(point_migration[scientific],points[scientific])
    if point_migration.target_source_record_id.duplicated().any() or not set(point_migration.target_source_record_id).issubset(result.source_record_id):raise ValueError('Point endpoint migration invalid')
    evidence=pd.read_parquet(evidence_path);new_evidence=evidence.copy()
    new_evidence['source_record_id']=evidence.source_record_id.map(lambda rid:mapping.get(rid,rid))
    fresh=result[result.displaced_source_record_id.notna()].set_index('displaced_source_record_id')
    current=result.set_index('source_record_id')
    protected=set(selected.loc[selected.population_value_quality.eq('confidentiality_perturbed_within_ten'),'source_record_id'])
    for i,old in zip(evidence.index,evidence.source_record_id):
        if old not in mapping and old not in protected:continue
        e=json.loads(evidence.at[i,'source_evidence_json'])
        r=current.loc[mapping.get(old,old)]
        e['population_value_quality_original_tag']=r.population_value_quality_original_tag
        e['population_quality_limitation']=r.population_quality_limitation
        e['population_value_quality']=r.population_value_quality
        if old not in mapping:
            new_evidence.at[i,'source_evidence_json']=json.dumps(e,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            continue
        for c in ['source_record_id','source_file','source_path','source_sha256','source_locator','source_sheet','source_row',
                  'source_native_id','source_name_raw','source_population_raw','population','population_value_quality',
                  'district_raw','population_scope','entity_grain_status','source_selection_component','men','women','source_raw_line']:
            v=r.get(c);e[c]=None if pd.isna(v) else v
        e.update({'publication_binding_old_source_record_id':old,'publication_binding_review_sha256':pins['review']['sha256'],
                  'legacy_quality_join_status':'inherited_via_reviewed_same_census_publication_binding','grain_explicit':True,
                  'grain_review_flag':'primary_atomic_settlement_reviewed'})
        new_evidence.at[i,'source_evidence_json']=json.dumps(e,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    if not new_evidence.source_record_id.is_unique or set(new_evidence.source_record_id)!=set(result.source_record_id):raise ValueError('Source evidence exact ID set differs from new selection')
    output.mkdir(parents=True)
    tables={'selected_observations.parquet':result,'accepted_identity_edges.parquet':migrated,
            'accepted_point_uses.parquet':point_migration,'source_evidence.parquet':new_evidence,
            'accepted_publication_bindings.parquet':bindings,
            'displaced_population_assertions.parquet':selected[selected.source_record_id.isin(mapping)]}
    for name,d in tables.items():d.to_parquet(output/name,index=False)
    receipt={'status':'reviewed_primary_2010_replacements_applied','inputs':pins,'builder_sha256':sha(Path(__file__)),
             'bindings':len(bindings),'selected_rows_before':len(selected),'selected_rows_after':len(result),
             '2010_known_population_before':int(selected.loc[selected.census_year.eq(2010),'population'].sum()),
             '2010_known_population_after':int(result.loc[result.census_year.eq(2010),'population'].sum()),
             'primary_population_delta':int(bindings.population_delta.sum()),
             'migrated_edge_endpoints':int(graph.from_source_record_id.isin(mapping).sum()+graph.to_source_record_id.isin(mapping).sum()),
             'migrated_point_targets':int(points.target_source_record_id.isin(mapping).sum()),
             'identity_decisions_and_point_origins_unchanged':True,
             'outputs':{name:{'path':str(output/name),'sha256':sha(output/name),'rows':len(d)} for name,d in tables.items()},
             'limits':['No regional residual allocation or extra cross-year identity proof.','Old population assertions preserved with original source quality.',
                       'Unreplaced protected values retain their old tag separately; exact scope and precision remain unverified.']}
    (output/'acceptance_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return {k:v for k,v in receipt.items() if k not in ['inputs','outputs','limits']}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ['selected','graph','points','evidence','proposals','review','output']:ap.add_argument('--'+key,required=True,type=Path)
    a=ap.parse_args();print(json.dumps(apply(a.selected,a.graph,a.points,a.evidence,a.proposals,a.review,a.output),ensure_ascii=False))
