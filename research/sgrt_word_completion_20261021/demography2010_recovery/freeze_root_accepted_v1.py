#!/usr/bin/env python3
"""Freeze root-reviewed source additions without rewriting the inherited source axis."""
from pathlib import Path
import hashlib,json,re
import pandas as pd
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2]
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    files={'bashkortostan':ROOT/'root_reviewed_primary2010_bash_strict3492.parquet',
           'tver':ROOT/'tver/immutable_source_review_candidates_tver_8683_20261021_v1.parquet',
           'vologda':ROOT/'vologda/immutable_source_review_candidates_vologda_4200_20261021_v1.parquet',
           'novgorod':ROOT/'novgorod/immutable_source_review_candidates_novgorod_2534_20261021_v1.parquet'}
    native=pd.read_parquet(REPO/'publication/stage71/applied_state_observations.parquet',columns=['source_record_id','census_year','settlement_name','settlement_type','region_norm'])
    native=native[native.census_year.eq(2010)].set_index('source_record_id')
    frames=[];reviews=[]
    for region,p in files.items():
        before=sha(p);d=pd.read_parquet(p)
        assert d.id.is_unique and d.source_record_id.is_unique and d.census_reference_date.eq('2010-10-14').all()
        assert not d.link_identity_uses_population.any() and not d.sex_sum_valid.eq(False).any()
        assert d.source_row_grain.eq('literal_settlement_not_municipal_aggregate').all()
        sample=ROOT/f'root_{region}_source_samples.json'
        if region=='bashkortostan':assert json.loads((ROOT/'root_bashkortostan_source_review.json').read_text())['approval_for_model_override']
        else:assert json.loads(sample.read_text())['passed']
        joined=d.merge(native[['settlement_name','settlement_type','region_norm']],left_on='axis_original_source_record_id_2010',right_index=True,suffixes=('','_native'),validate='one_to_one')
        assert len(joined)==len(d)
        assert joined.settlement_name.map(norm).eq(joined.settlement_name_native.map(norm)).all()
        assert joined.settlement_type.map(norm).eq(joined.settlement_type_native.map(norm)).all()
        assert joined.region.map(norm).eq(joined.region_norm.map(norm)).all()
        source=Path(d.source_path.iloc[0]);assert sha(source)==d.source_sha256.iloc[0]
        if region=='bashkortostan':
            values=d.primary_population;quality=pd.Series('reviewed_primary_reported_value',index=d.index);derived=pd.Series(False,index=d.index)
        else:
            values=d.population_for_root_review;quality=d.proposed_primary_value_quality;derived=d.derived_zero_from_exhaustive_same_scope_controls.fillna(False)
            proof=json.loads((ROOT/region/'derived_zero_proof_receipt.json').read_text())
            assert proof['raw_primary_population_preserved_NULL']
            if region=='tver':assert proof['all_district_NP_counts_match'] and proof['all_district_zero_counts_match'] and proof['numeric_settlement_population_sum']==proof['source_total_population']
            elif region=='vologda':assert proof['all_six_population_group_controls_match'] and proof['region_population_control']==proof['region_population_NP_sum'] and proof['rural_population_control']==proof['rural_population_NP_sum']
            else:assert proof['all_21_district_NP_type_count_controls_match'] and proof['all_21_district_uninhabited_controls_match'] and proof['all_21_district_population_sums_match']
            assert d.loc[derived,'primary_population'].isna().all() and values[derived].eq(0).all()
        assert values.notna().all() and values.ge(0).all() and (values%1).eq(0).all()
        already_primary=d.baseline_original_quality.ne('secondary_confidentiality_protected_value_exact_scope_unverified')
        assert values[already_primary].eq(d.loc[already_primary,'baseline_original_secondary_population']).all()
        d['reviewed_primary2010_population']=values;d['reviewed_primary2010_quality']=quality
        d['reviewed_primary2010_override_allowed']=True;d['root_review_status']='accepted_primary_same2010_unique_name_type_region'
        d['not_model_input_without_root_review']=False;d['parent_root_review_required_before_model_override']=False
        d['root_review_native2010_name_type_region_verified']=True;d['root_review_zero_proof_required_and_verified']=derived
        d['root_review_source_layer_sha256']=before
        assert sha(p)==before
        changes=values.ne(d.baseline_original_secondary_population)
        reviews.append({'region':region,'rows':len(d),'source_layer':str(p.relative_to(ROOT)),'source_layer_sha256':before,'primary_source_sha256':d.source_sha256.iloc[0],'previously_secondary':int((~already_primary).sum()),'changed_numeric_values':int(changes.sum()),'control_derived_zeros':int(derived.sum()),'native2010_name_type_region_all_agree':True})
        frames.append(d)
    combined=pd.concat(frames,ignore_index=True,sort=False);assert combined.id.is_unique
    p=ROOT/'root_reviewed_primary2010_four_regions_v1.parquet';temporary=p.with_suffix('.parquet.building');combined.to_parquet(temporary,index=False);temporary.replace(p)
    receipt={'status':'ROOT_REVIEW_ACCEPTED_SOURCE_SUPPLEMENT','reviewer':'root','source_regions':reviews,'rows':len(combined),'new_primary_previously_secondary':sum(x['previously_secondary'] for x in reviews),'changed_numeric_values':sum(x['changed_numeric_values'] for x in reviews),'control_derived_zeros':sum(x['control_derived_zeros'] for x in reviews),'supplement_sha256':sha(p),'raw_axis_modified':False,'historical2010_to2021_boundary_equivalence_proven':False,'scope':'Literal2010counts or control-provenzero for unique same2010source-NP identities; preserves original values and all source locators'}
    (ROOT/'root_four_regions_admission_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
