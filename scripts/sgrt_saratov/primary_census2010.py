"""Cross-check original Saratov 2010 records against a frozen primary table.

The immutable census foundation is read, never rewritten. Identity matching uses
original 2010 typed names, unique independently in both provincial frames; no
2021 name/district, population value or expected demographic result is a key.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_field_pilot.input_inventory import catalog_source

POPULATION_MEMBER='data/population/settlements_census_long.parquet'
SOURCE_ROOT=REPO/'references/primary/saratov_census2010'
KIND=r'(?:железнодорожный\s+разъезд|железнодорожная\s+станция|насел[еёѐ]нный\s+пункт|пос[еёѐ]лок\s+городского\s+типа|г\.|пгт|[cс]ело|деревня|хутор|станция|разъезд|пос[еёѐ]лок)'
NUMBER=r'(?:\d+|[-–—…]+|\.{3})'
PERCENT=r'(?:\d+(?:,\d+)?|[-–—…]+|\.{3})'
NAME=rf'(?P<name>(?:(?!(?-i:\b{KIND}\s)|сельское\s+поселение|городское\s+поселение|Всего\s+по\s+району).)+?)'
ROW=re.compile(rf'(?<!\w)(?P<kind>{KIND})\s+{NAME}\s+(?P<total>{NUMBER})\s+(?P<male>{NUMBER})\s+(?P<female>{NUMBER})\s+(?P<mp>{PERCENT})\s+(?P<fp>{PERCENT})',re.I)
DISTRICT=re.compile(r'^([А-ЯЁА-яёѐ -]+ район)\s*$',re.M)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(value):
    if value is None or pd.isna(value):return ''
    text=str(value).casefold().replace('ё','е').replace('ѐ','е').replace('–','-').replace('—','-')
    return re.sub(r'\s+',' ',text).strip()


def kind_key(value):
    value=norm(value)
    aliases={'г.':'город','cело':'село','поселок':'поселок',
        'поселок городского типа':'пгт','населенный пункт':'населенный пункт',
        'железнодорожный разъезд':'железнодорожный объект',
        'железнодорожная станция':'железнодорожный объект'}
    return aliases.get(value,value)


def name_key(value):
    # This literal is a population-scope annotation in the Mikhailovsky row,
    # not part of the named settlement. The raw label remains in the output.
    value=re.sub(r'\s*\(сельское население\)\s*$','',str(value),flags=re.I)
    return norm(value)


def count_value(value):
    return int(value) if value.isdigit() else 0 if value in {'-','–','—'} else None


def parse_reader(text):
    title='Численность населения по городским и сельским населенным пунктам на 14 октября 2010 г.'
    start=text.index(title);end=text.index('Методологические пояснения',start)
    body=text[start:end];districts=list(DISTRICT.finditer(body));rows=[]
    for match in ROW.finditer(body):
        previous=body[max(0,match.start()-80):match.start()]
        if re.search(r'(?:Городской\s+округ|Городское\s+поселение)\s*$',previous,re.I):continue
        contexts=[d for d in districts if d.start()<match.start()]
        district=contexts[-1][1] if contexts else 'Городские округа'
        values={k:count_value(match[k]) for k in ['total','male','female']}
        absolute=start+match.start()
        rows.append({'primary_row_id':f'SARATOVSTAT2010:np_table:{len(rows)+1:04d}',
            'primary_name_literal':match['name'],'primary_kind_literal':match['kind'],
            'name_key':name_key(match['name']),'kind_key':kind_key(match['kind']),
            'primary_population_2010':values['total'],'primary_male_2010':values['male'],
            'primary_female_2010':values['female'],
            'primary_male_percent_literal':match['mp'],'primary_female_percent_literal':match['fp'],
            'male_plus_female_equals_total':all(v is not None for v in values.values()) and values['total']==values['male']+values['female'],
            'primary_district_by_reader_position':district,
            'reader_character_start':absolute,'reader_character_end':start+match.end(),
            'reader_line_1based':text.count('\n',0,absolute)+1,
            'reader_row_literal':text[absolute:start+match.end()],
            'primary_table_date':'2010-10-14','source_is_primary_publication_content':True,
            'primary_pdf_binary_read_locally':False})
    frame=pd.DataFrame(rows);controls=[]
    for d in districts:
        following=[x for x in districts if x.start()>d.start()]
        block=body[d.end():following[0].start() if following else len(body)]
        total=re.search(r'Всего по району\s+(?:Сельское население\s+)?(\d+)\s+(\d+)\s+(\d+)',block)
        selected=frame[frame.primary_district_by_reader_position.eq(d[1])]
        expected=int(total[1]) if total else None
        observed=int(selected.primary_population_2010.sum())
        controls.append({'primary_district_header':d[1],'published_district_population_2010':expected,
            'sum_np_by_reader_heading_position':observed,'difference':observed-expected if expected is not None else None,
            'district_context_reconciled':expected is not None and observed==expected,
            'np_rows':len(selected),'reader_context_correction_applied':False})
    controls=pd.DataFrame(controls)
    good=set(controls.loc[controls.district_context_reconciled,'primary_district_header'])
    frame['reader_district_context_reconciled']=frame.primary_district_by_reader_position.isin(good)
    frame['reader_district_context_status']=np.where(frame.primary_district_by_reader_position.eq('Городские округа'),
        'separate_urban_okrugs_not_a_district_sum',np.where(frame.reader_district_context_reconciled,
        'published_district_total_reconciled','held_reader_order_context_does_not_reconcile'))
    return frame,controls


def compare_legacy(primary,legacy):
    legacy=legacy[legacy.census_year.eq(2010)&legacy.region_norm.eq('саратовская')].copy()
    if legacy.source_record_id.duplicated().any():raise ValueError('Original 2010 record identity duplicated')
    legacy['name_key']=legacy.settlement_name.map(name_key);legacy['kind_key']=legacy.settlement_type.map(kind_key)
    pcounts=primary.groupby(['kind_key','name_key']).size().to_dict()
    lcounts=legacy.groupby(['kind_key','name_key']).size().to_dict()
    unique={key:group.iloc[0].to_dict() for key,group in primary.groupby(['kind_key','name_key']) if len(group)==1}
    rows=[]
    for r in legacy.to_dict('records'):
        key=(r['kind_key'],r['name_key']);pc=pcounts.get(key,0);lc=lcounts[key]
        candidate=unique.get(key) if pc==lc==1 else None
        base=r.get('effective_population',r.get('population'))
        value=candidate['primary_population_2010'] if candidate else None
        comparable=candidate is not None and candidate['male_plus_female_equals_total'] and value is not None
        status='unique_original_2010_type_name_both_province_frames' if comparable else 'primary_literal_not_found' if not pc else 'ambiguous_original_2010_type_name_held'
        row={'source_record_id_2010':r['source_record_id'],'legacy_name_literal':r['settlement_name'],
            'legacy_kind_literal':r['settlement_type'],'legacy_district_literal':r.get('district_raw'),
            'name_key':key[1],'kind_key':key[0],'legacy_population_2010':base,
            'legacy_population_value_quality_2010':r.get('population_value_quality'),
            'legacy_source_file':r.get('source_file'),'legacy_source_locator':r.get('source_locator'),
            'primary_type_name_candidate_count':pc,'legacy_type_name_record_count':lc,
            'identity_match_status':status,'primary_value_admissible_in_separate_derived_variant':bool(comparable),
            'primary_population_2010':value,'primary_minus_legacy':float(value)-float(base) if comparable and pd.notna(base) else None,
            'primary_equals_legacy':bool(value==base) if comparable and pd.notna(base) else None,
            'matched_using_2021_name_or_district':False,'population_value_used_as_identity_key':False,
            'intercensus_chain_or_boundary_equality_proved':False,'base_population_written_or_modified':False,
            'population_scope_comparability_unverified':True,
            'primary_publication_population_rule_includes_institutional_residents':True,
            'institutional_population_of_this_np_independently_known':False,
            'difference_is_not_automatically_a_legacy_error_or_imputation':True}
        if candidate:
            row.update({k:v for k,v in candidate.items() if k not in ['name_key','kind_key','primary_population_2010']})
        rows.append(row)
    return pd.DataFrame(rows)


def run(population_long,output,reader=SOURCE_ROOT/'reader_extract.txt'):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=json.loads((SOURCE_ROOT/'provenance.json').read_text())
    if sha(reader)!=source['frozen_reader_sha256'] or Path(reader).stat().st_size!=source['frozen_reader_bytes']:
        raise ValueError('Primary reader bytes differ from frozen source')
    spec=catalog_source(REPO/'data/catalog.json',POPULATION_MEMBER)
    if sha(population_long)!=spec['sha256'] or Path(population_long).stat().st_size!=spec['bytes']:
        raise ValueError('Immutable census foundation differs')
    primary,controls=parse_reader(Path(reader).read_text())
    facts={'np_rows':len(primary),'urban_np_rows':int(primary.kind_key.isin(['город','пгт']).sum()),
        'rural_np_rows':int((~primary.kind_key.isin(['город','пгт'])).sum()),
        'published_zero_np_rows':int(primary.primary_population_2010.eq(0).sum()),
        'sum_np_population_2010':int(primary.primary_population_2010.sum()),
        'all_male_plus_female_checks_pass':bool(primary.male_plus_female_equals_total.all())}
    if facts!={'np_rows':1823,'urban_np_rows':45,'rural_np_rows':1778,'published_zero_np_rows':95,'sum_np_population_2010':2521892,'all_male_plus_female_checks_pass':True}:
        raise ValueError('Parsed primary records differ from published source-level controls: '+str(facts))
    comparison=compare_legacy(primary,pd.read_parquet(population_long))
    eligible=comparison.primary_value_admissible_in_separate_derived_variant
    tables={'primary_np_rows.parquet':primary,'district_reader_controls.parquet':controls,'population_2010_evidence.parquet':comparison}
    for name,frame in tables.items():frame.to_parquet(output/name,index=False,compression='zstd')
    comparison.to_csv(output/'population_2010_comparison.csv',index=False)
    summary={'schema':'sgrt.saratov.primary_census2010_comparison.v1','source':source,'foundation_source':spec,
        'primary_table_controls':facts,'legacy_original_2010_np_records':len(comparison),
        'identity_status_counts':comparison.identity_match_status.value_counts().to_dict(),
        'unique_matched_records':int(eligible.sum()),
        'matched_equal_legacy_values':int(comparison.loc[eligible,'primary_equals_legacy'].eq(True).sum()),
        'matched_different_legacy_values':int(comparison.loc[eligible,'primary_equals_legacy'].eq(False).sum()),
        'largest_absolute_matched_difference':float(comparison.loc[eligible,'primary_minus_legacy'].abs().max()),
        'reconciled_district_reader_contexts':int(controls.district_context_reconciled.sum()),
        'held_district_reader_contexts':controls.loc[~controls.district_context_reconciled,'primary_district_header'].tolist(),
        'source_2010_names_only_not_2021':True,'population_value_used_as_identity_key':False,
        'frozen_population_base_modified':False,'new_evidence_does_not_independently_prove_intercensus_links_or_boundary_equality':True,
        'tables':{name:{'rows':len(frame),'sha256':sha(output/name)} for name,frame in tables.items()}}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def compare_context_variants(baseline,primary,output):
    """Compare the same NP/centre compositions under two2010 number sources."""
    baseline,primary,output=Path(baseline),Path(primary),Path(output)
    output.mkdir(parents=True,exist_ok=True)
    old=pd.read_parquet(baseline/'np_context.parquet').set_index('source_record_id')
    new=pd.read_parquet(primary/'np_context.parquet').set_index('source_record_id')
    if set(old.index)!=set(new.index):raise ValueError('NP roster differs between2010 scenarios')
    new=new.loc[old.index]
    for col in ['population_2002','population_2021','source_record_id_2010','credit_2002','credit_2010','credit_2021','budget_population_credit']:
        if not old[col].equals(new[col]):raise ValueError('2010 variant changed another foundation axis: '+col)
    detail=pd.DataFrame({'source_record_id':old.index,'name':old.name.to_numpy(),
        'primary2010_evidence_applied':new.primary2010_derived_evidence_applied.to_numpy(),
        'legacy_population_2010':old.population_2010.to_numpy(),
        'primary_variant_population_2010':new.population_2010.to_numpy(),
        'primary_minus_legacy':new.population_2010.to_numpy()-old.population_2010.to_numpy(),
        'population_scope_comparability_unverified':True})
    for mode in ['accepted','strict']:
        col=f'demographic_trajectory_2002_2010_2021_{mode}'
        detail['baseline_trajectory_'+mode]=old[col].to_numpy()
        detail['primary_variant_trajectory_'+mode]=new[col].to_numpy()
    detail['both_accepted_three_point_sequences_complete']=detail.baseline_trajectory_accepted.ne('unknown')&detail.primary_variant_trajectory_accepted.ne('unknown')
    detail['accepted_three_point_sequence_changed']=detail.both_accepted_three_point_sequences_complete&detail.baseline_trajectory_accepted.ne(detail.primary_variant_trajectory_accepted)
    for start,end in [(2002,2010),(2010,2021)]:
        for variant,frame in [('baseline',old),('primary_variant',new)]:
            col=f'annualized_population_change_percent_{start}_{end}_accepted'
            detail[f'{variant}_annualized_change_percent_{start}_{end}']=frame[col].to_numpy()
    oc=pd.read_parquet(baseline/'basic_centre_dynamic_types.parquet').set_index('centre_id')
    nc=pd.read_parquet(primary/'basic_centre_dynamic_types.parquet').set_index('centre_id')
    if set(oc.index)!=set(nc.index):raise ValueError('Known NP centres differ between2010 scenarios')
    nc=nc.loc[oc.index]
    for col in ['external_positive_origin_count','external_rural_positive_origin_count','centre_in_regional_roster']:
        if not oc[col].equals(nc[col]):raise ValueError('Basic centre composition changed in2010 scenario')
    # Component population membership counts must also match each scope/period.
    ac=pd.read_parquet(baseline/'basic_centre_demographic_components.parquet')
    bc=pd.read_parquet(primary/'basic_centre_demographic_components.parquet')
    axes=['centre_id','component','start_year','end_year','evidence_mode']
    if not ac.sort_values(axes)[axes+['records']].reset_index(drop=True).equals(bc.sort_values(axes)[axes+['records']].reset_index(drop=True)):
        raise ValueError('Basic centre component membership axes changed')
    centres=pd.DataFrame({'centre_id':oc.index,'centre_name':oc.centre_name.to_numpy(),
        'centre_in_regional_roster':oc.centre_in_regional_roster.to_numpy(),
        'external_unique_origins':oc.external_positive_origin_count.to_numpy(),
        'population_scope_comparability_unverified':True,'numeric_primary_is_not_full_temporal_comparability':True})
    for variant,frame in [('baseline',oc),('primary_variant',nc)]:
        for mode in ['accepted','strict']:
            for scope in ['centre','rural_external']:
                col=f'{scope}_trajectory_2002_2010_2021_{mode}'
                centres[f'{variant}_{scope}_trajectory_{mode}']=frame[col].to_numpy()
                for start,end in [(2002,2010),(2010,2021)]:
                    rate=f'{scope}_annualized_change_percent_{start}_{end}_{mode}'
                    centres[f'{variant}_{scope}_annualized_percent_{start}_{end}_{mode}']=frame[rate].to_numpy()
    for variant in ['baseline','primary_variant']:
        for mode in ['accepted','strict']:
            a=centres[f'{variant}_centre_trajectory_{mode}'];b=centres[f'{variant}_rural_external_trajectory_{mode}']
            valid=a.ne('unknown')&b.ne('unknown')
            centres[f'{variant}_complete_centre_rural_trajectory_{mode}']=valid
            centres[f'{variant}_centre_rural_trajectory_{mode}']=(a+'|'+b).where(valid,'unknown')
    same=centres.baseline_complete_centre_rural_trajectory_accepted&centres.primary_variant_complete_centre_rural_trajectory_accepted
    centres['same_complete_accepted_composition_cohort']=same
    centres['accepted_centre_rural_trajectory_changed']=same&centres.baseline_centre_rural_trajectory_accepted.ne(centres.primary_variant_centre_rural_trajectory_accepted)
    centres['same_new_numeric_primary_complete_cohort']=same&centres.primary_variant_complete_centre_rural_trajectory_strict
    applied=detail.primary2010_evidence_applied.eq(True)
    np_cohort=applied&detail.both_accepted_three_point_sequences_complete
    regional=centres.centre_in_regional_roster.eq(True)
    centre_cohort=regional&centres.same_new_numeric_primary_complete_cohort
    tables={'np_trajectory_comparison.parquet':detail,'basic_centre_trajectory_comparison.parquet':centres}
    for name,frame in tables.items():frame.to_parquet(output/name,index=False,compression='zstd')
    summary={'schema':'sgrt.saratov.primary2010_trajectory_comparison.v1',
        'current_np_records':len(detail),'primary2010_applied_current_records':int(applied.sum()),
        'primary2010_changed_current_values':int((applied&detail.primary_minus_legacy.ne(0)).sum()),
        'matched_np_same_complete_accepted_three_point_cohort':int(np_cohort.sum()),
        'matched_np_accepted_sequence_changes_in_same_cohort':int(detail.loc[np_cohort,'accepted_three_point_sequence_changed'].sum()),
        'regional_np_centres':int(regional.sum()),
        'baseline_regional_complete_numeric_primary_centre_rural_trajectories':int(centres.loc[regional,'baseline_complete_centre_rural_trajectory_strict'].sum()),
        'new_regional_complete_numeric_primary_centre_rural_trajectories':int(centres.loc[regional,'primary_variant_complete_centre_rural_trajectory_strict'].sum()),
        'regional_same_complete_accepted_centre_rural_cohort':int((regional&same).sum()),
        'regional_accepted_centre_rural_trajectory_changes_same_cohort':int(centres.loc[regional&same,'accepted_centre_rural_trajectory_changed'].sum()),
        'regional_same_new_numeric_primary_complete_cohort':int(centre_cohort.sum()),
        'regional_trajectory_changes_in_same_new_numeric_primary_complete_cohort':int(centres.loc[centre_cohort,'accepted_centre_rural_trajectory_changed'].sum()),
        'new_numeric_primary_cohort_reported_centre_rural_sequences':centres.loc[centre_cohort,'primary_variant_centre_rural_trajectory_strict'].value_counts().to_dict(),
        'census_foundation_modified':False,'2021_population_or_functional_compositions_changed':False,
        'population_scope_comparability_unverified':True,
        'interpretation':'Reported-total2010 source scenario with explicit geographic name linkage. Numeric primary confirmation does not establish unchanged boundaries, comparable population scopes, or causal service/demographic effects. Differences are not automatically legacy errors.',
        'tables':{name:{'rows':len(frame),'sha256':sha(output/name)} for name,frame in tables.items()}}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--population-long',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--reader',type=Path,default=SOURCE_ROOT/'reader_extract.txt')
    p.add_argument('--compare-baseline',type=Path);p.add_argument('--compare-primary',type=Path)
    a=p.parse_args()
    if a.compare_baseline is not None or a.compare_primary is not None:
        if a.compare_baseline is None or a.compare_primary is None:p.error('Both context comparison directories are required')
        result=compare_context_variants(a.compare_baseline,a.compare_primary,a.output)
    else:
        if a.population_long is None:p.error('--population-long is required for primary-source extraction')
        result=run(a.population_long,a.output,a.reader)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
