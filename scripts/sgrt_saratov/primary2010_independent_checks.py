"""Independent reading controls for the Saratovstat2012 census2010 NP table.

No 2021 district, nearest coordinate or population value selects an identity.
This checker keeps the reader's municipal-order defects visible; numeric
agreement alone cannot validate an NP identity or repair a missing row.
"""
from __future__ import annotations
import argparse,hashlib,json,math,re
from pathlib import Path
from collections import Counter

READER_SHA='42fed92574010d8d395970f1fb32f10f782a6073cfdc36af05e28d477114cae8'
SOURCE_URL='https://64.rosstat.gov.ru/storage/mediabank/NXk1R9IJ/Численность+и+размещение.pdf'
TYPES=['железнодорожный разъезд','железнодорожная станция','поселок городского типа',
       'населенный пункт','станция','разъезд','деревня','хутор','поселок','пгт','село','cело','г.']


def normalize(value):
    return re.sub(r'\s+',' ',str(value).casefold().replace('ё','е').replace('ѐ','е')).strip()


def number(value):
    if value.isdigit():return int(value)
    if value in {'-','–','—'}:return 0
    return None


def independent_rows(text):
    """First identify type anchors, then independently decode their first cell run."""
    title='Численность населения по городским и сельским населенным пунктам на 14 октября 2010 г.'
    begin=text.index(title)+len(title)
    end=text.find('Методологические пояснения',begin)
    if end<0:raise ValueError('Missing explicit end of NP table')
    body=text[begin:end]
    # Preserve capitals: "Село" within a proper name is not a new type anchor.
    typed=[re.escape(t).replace('поселок',r'пос[еёѐ]лок').replace('населенный',r'насел[еёѐ]нный') for t in TYPES]
    anchors=list(re.finditer(r'(?<![А-Яа-яA-Za-z])(?:'+ '|'.join(typed)+r')\s+',body))
    integer=r'(?:\d+|[-–—…]|\.{3})';percent=r'(?:\d+,\d+|[-–—…]|\.{3})'
    cells=re.compile(r'(?<![\w,])('+integer+r')\s+('+integer+r')\s+('+integer+r')\s+('+percent+r')\s+('+percent+r')')
    headings=list(re.finditer(r'^\s*([А-ЯЁА-Яа-яёѐ -]+район)\s*$',body,re.M))
    rows=[];held=[]
    for index,anchor in enumerate(anchors):
        prior=body[max(0,anchor.start()-90):anchor.start()]
        if re.search(r'(?:Городской\s+округ|Городское\s+поселение)\s*$',prior,re.I):continue
        limit=anchors[index+1].start() if index+1<len(anchors) else len(body)
        segment=body[anchor.end():limit];values=cells.search(segment)
        if values is None:held.append({'position':begin+anchor.start(),'reason':'no_complete_population_sex_percentage_cells'});continue
        name=segment[:values.start()].strip()
        if re.search(r'сельское поселение|городское поселение|Всего по району|Муж-чины|Продолжение',name,re.I):
            held.append({'position':begin+anchor.start(),'reason':'name_crosses_table_structure','name':name});continue
        district='Городские округа'
        for heading in headings:
            if heading.start()>anchor.start():break
            district=heading[1].strip()
        total,male,female=map(number,values.group(1,2,3))
        scope=normalize(anchor.group().strip()).replace('cело','село')
        rows.append({'kind':scope,'name':name,'district':district,'population':total,'male':male,'female':female,
            'male_percent_literal':values[4],'female_percent_literal':values[5],
            'source_character_start':begin+anchor.start(),'source_character_end':begin+anchor.end()+values.end()})
    return rows,held,body


def audit(reader_path,parsed_path=None,evidence_path=None,population_long=None):
    content=Path(reader_path).read_bytes()
    if hashlib.sha256(content).hexdigest()!=READER_SHA:raise ValueError('Frozen census reader extract differs')
    rows,held,body=independent_rows(content.decode());errors=[];municipal=[]
    if len(rows)!=1823:errors.append('Independent typed NP count differs from book45urban+1778rural')
    urban=sum(r['kind'] in {'г.','пгт','поселок городского типа'} for r in rows)
    zero=sum(r['population']==0 for r in rows)
    if urban!=45 or len(rows)-urban!=1778 or zero!=95:errors.append('Independent urban/rural/zero counts differ from separate book summary')
    if any(r['population'] is None or r['male'] is None or r['female'] is None or r['male']+r['female']!=r['population'] for r in rows):errors.append('An NP total differs from male+female or is unknown')
    total=sum(r['population'] or 0 for r in rows)
    if total!=2521892:errors.append('Whole-province sum differs from separate census total')
    percentage_mismatches=[]
    for row in rows:
        if not row['population']:continue
        for kind,quantity in [('male',row['male']),('female',row['female'])]:
            literal=row[kind+'_percent_literal']
            if ',' in literal and abs(float(literal.replace(',','.'))-100.*quantity/row['population'])>.05000001:
                percentage_mismatches.append((row['kind'],row['name'],kind))
    if percentage_mismatches:errors.append({'sex_percentage_rounding_mismatches':percentage_mismatches})
    district_total=re.compile(r'^\s*([А-ЯЁА-Яа-яёѐ -]+район)\s*$',re.M)
    headings=list(district_total.finditer(body))
    for index,heading in enumerate(headings):
        stop=headings[index+1].start() if index+1<len(headings) else len(body)
        block=body[heading.end():stop];m=re.search(r'Всего\s+по\s+району\s+(?:Сельское\s+население\s+)?(\d+)\s+(\d+)\s+(\d+)',block)
        if not m:errors.append('No explicit district total: '+heading[1]);continue
        expected=int(m[1]);observed=sum(r['population'] or 0 for r in rows if r['district']==heading[1].strip())
        municipal.append({'district':heading[1].strip(),'published_total':expected,'reader_order_sum':observed,'difference':observed-expected})
    differences=[r for r in municipal if r['difference']]
    # These are held reader-order defects, never silently repaired by this checker.
    expected_defects={'Духовницкий район':-652,'Екатериновский район':652}
    if {r['district']:r['difference'] for r in differences}!=expected_defects:errors.append('New or changed municipal-order discrepancy')
    text=content.decode();overview_start=text.index('Характеристика муниципальных районов на 14 октября 2010 г.')
    overview_end=text.index('Число сельских поселе-',overview_start)
    overview=normalize(text[overview_start:overview_end]);count_checks=[]
    for heading in headings:
        district=heading[1].strip();short=normalize(district.removesuffix(' район'))
        pattern=r'(?<![а-я])'+re.escape(short)+r'\s+(\d+|-)\s+(\d+|-)\s+(\d+)\s+(\d+|-)\s+\d+,\d+\s+\d+,\d+'
        m=re.search(pattern,overview)
        if not m:errors.append('Independent municipal NP-count row not found '+district);continue
        group=[r for r in rows if r['district']==district]
        rural_rows=[r for r in group if r['kind'] not in {'г.','пгт','поселок городского типа'}]
        expected_rural=int(m[3]);expected_zero=number(m[4]);actual_zero=sum(r['population']==0 for r in rural_rows)
        count_checks.append({'district':district,'published_rural_np':expected_rural,'reader_rural_np':len(rural_rows),
            'published_zero_rural_np':expected_zero,'reader_zero_rural_np':actual_zero,
            'rural_count_difference':len(rural_rows)-expected_rural,'zero_count_difference':actual_zero-expected_zero})
    displaced={r['district']:(r['rural_count_difference'],r['zero_count_difference']) for r in count_checks if r['rural_count_difference'] or r['zero_count_difference']}
    if displaced!={'Духовницкий район':(-3,-1),'Екатериновский район':(3,1)}:errors.append({'new_municipal_np_count_discrepancy':displaced})
    compared=0
    if parsed_path is not None:
        import pandas as pd
        parsed=pd.read_parquet(parsed_path) if Path(parsed_path).suffix=='.parquet' else pd.read_csv(parsed_path)
        indexed={int(r['source_character_start']):r for r in rows}
        if len(parsed)!=len(rows) or set(parsed.reader_character_start.astype(int))!=set(indexed):errors.append('Production primary table source-character identities differ')
        for row in parsed.itertuples(index=False):
            expected=indexed.get(int(row.reader_character_start))
            if expected is None:continue
            actual=(normalize(row.primary_kind_literal).replace('cело','село'),normalize(row.primary_name_literal),int(row.primary_population_2010),int(row.primary_male_2010),int(row.primary_female_2010),row.primary_district_by_reader_position)
            wanted=(expected['kind'],normalize(expected['name']),expected['population'],expected['male'],expected['female'],expected['district'])
            if actual!=wanted:errors.append('Production primary row differs from independent anchor/cell parser: '+str(row.primary_row_id))
        compared=len(parsed)
    evidence_count=matched_count=different_count=0
    if evidence_path is not None:
        if population_long is None:raise ValueError('Original2010long records required for independent identity comparison')
        import pandas as pd
        population_long=Path(population_long)
        if hashlib.sha256(population_long.read_bytes()).hexdigest()!='2b0a1e3cd20819f6b99d1e6a200e4365fa7296e128dc22b023327b9e572f60c4':raise ValueError('Original population-long snapshot differs')
        legacy=pd.read_parquet(population_long,filters=[('census_year','=',2010)])
        legacy=legacy[legacy.region_norm.eq('саратовская')]
        def name_key(value):return re.sub(r'\s*\(сельское население\)\s*$','',normalize(value)).strip()
        def kind_key(value):
            value=normalize(value).replace('cело','село')
            return {'г.':'город','поселок городского типа':'пгт','железнодорожная станция':'железнодорожный объект','железнодорожный разъезд':'железнодорожный объект'}.get(value,value)
        by_key={}
        for row in rows:by_key.setdefault((kind_key(row['kind']),name_key(row['name'])),[]).append(row)
        legacy_keys=Counter((kind_key(r.settlement_type),name_key(r.settlement_name)) for r in legacy.itertuples(index=False))
        evidence=pd.read_parquet(evidence_path);by_id=evidence.set_index('source_record_id_2010')
        if not by_id.index.is_unique or set(by_id.index)!=set(legacy.source_record_id):errors.append('Original2010source-ID evidence inventory differs')
        for row in legacy.itertuples(index=False):
            key=(kind_key(row.settlement_type),name_key(row.settlement_name));primary=by_key.get(key,[])
            matched=len(primary)==1 and legacy_keys[key]==1
            actual=by_id.loc[row.source_record_id]
            if bool(actual.primary_value_admissible_in_separate_derived_variant)!=matched:errors.append('Population-dependent or nonunique primary identity selected '+str(row.source_record_id))
            if bool(actual.matched_using_2021_name_or_district) or bool(actual.population_value_used_as_identity_key) or bool(actual.base_population_written_or_modified):errors.append('Forbidden identity/value modification flag '+str(row.source_record_id))
            if matched:
                matched_count+=1;expected=primary[0]['population']
                if float(actual.primary_population_2010)!=float(expected):errors.append('Matched primary number differs from raw source '+str(row.source_record_id))
                base=getattr(row,'effective_population',row.population)
                if pd.notna(base) and float(base)!=float(expected):different_count+=1
        evidence_count=len(evidence)
    return {'schema':'sgrt.saratov.primary2010_independent.v1','source_reader_sha256':READER_SHA,'source_url':SOURCE_URL,
        'independent_typed_np_rows':len(rows),'urban_np':urban,'rural_np':len(rows)-urban,'published_zero_np':zero,
        'whole_province_population_sum':total,'sex_sum_rows_checked':len(rows),'sex_percentages_checked':sum(bool(r['population']) for r in rows)*2,
        'independent_unparsed_type_anchors':held,'municipal_checks':municipal,'reader_order_conflicts_held':differences,'municipal_np_count_checks':count_checks,
        'production_primary_rows_independently_compared':compared,'original_2010_evidence_records_compared':evidence_count,'independent_unique_2010_typed_name_matches':matched_count,'independent_primary_vs_legacy_different_numbers_not_errors':different_count,'errors':errors,'violations':len(errors),
        'scope':'Independent type-anchor/cell parser and separate book summary constraints. Two municipal total discrepancies and a zero-population context displacement require explicit holding; no source-value or NP-identity override.'}


def compare_contexts(base,primary,evidence,comparison):
    """Independently count same-composition trajectories, not a legacy error rate."""
    import numpy as np
    import pandas as pd
    base,primary,comparison=Path(base),Path(primary),Path(comparison)
    old=pd.read_parquet(base/'np_context.parquet').set_index('source_record_id')
    new=pd.read_parquet(primary/'np_context.parquet').set_index('source_record_id').loc[old.index]
    ev=pd.read_parquet(evidence).set_index('source_record_id_2010');errors=[]
    def sequence(row):
        numbers=[]
        for year in [2002,2010,2021]:
            value=row[f'population_{year}']
            if pd.isna(value) or not math.isfinite(float(value)) or float(value)<0 or pd.isna(row[f'source_record_id_{year}']) or row[f'credit_{year}']!=True or row['budget_population_credit']!=True:return 'unknown'
            numbers.append(float(value))
        directions=['growth' if b>a else 'decline' if b<a else 'unchanged' for a,b in zip(numbers[:-1],numbers[1:])]
        return '__'.join(directions)
    old_seq={sid:sequence(row) for sid,row in old.to_dict('index').items()}
    new_seq={sid:sequence(row) for sid,row in new.to_dict('index').items()}
    applied={sid:(row['source_record_id_2010'] in ev.index and bool(ev.loc[row['source_record_id_2010'],'primary_value_admissible_in_separate_derived_variant'])) for sid,row in old.to_dict('index').items()}
    cohort={sid for sid in old.index if applied[sid] and old_seq[sid]!='unknown' and new_seq[sid]!='unknown'}
    details=pd.read_parquet(comparison/'np_trajectory_comparison.parquet').set_index('source_record_id')
    if set(details.index)!=set(old.index):errors.append('Published NP comparison inventory differs')
    for sid,row in details.iterrows():
        if row.baseline_trajectory_accepted!=old_seq[sid] or row.primary_variant_trajectory_accepted!=new_seq[sid] or bool(row.primary2010_evidence_applied)!=applied[sid] or bool(row.both_accepted_three_point_sequences_complete)!=(old_seq[sid]!='unknown' and new_seq[sid]!='unknown'):
            errors.append('Published NP comparison source sequence differs '+str(sid))
    a=pd.read_parquet(base/'basic_centre_dynamic_types.parquet').set_index('centre_id')
    b=pd.read_parquet(primary/'basic_centre_dynamic_types.parquet').set_index('centre_id').loc[a.index]
    if set(a.index)!=set(b.index):errors.append('Basic centre composition inventory differs')
    for col in ['external_positive_origin_count','external_rural_positive_origin_count','centre_in_regional_roster']:
        if not a[col].equals(b[col]):errors.append('Centre composition changed between2010number sources '+col)
    def joint(row,mode):
        sequences=[]
        for component in ['centre','rural_external']:
            d1=row[f'{component}_direction_2002_2010_{mode}'];d2=row[f'{component}_direction_2010_2021_{mode}']
            if 'unknown' in (d1,d2):return 'unknown'
            sequences.append(d1+'__'+d2)
        return '|'.join(sequences)
    old_joint={sid:joint(row,'accepted') for sid,row in a.to_dict('index').items()}
    new_joint={sid:joint(row,'accepted') for sid,row in b.to_dict('index').items()}
    old_strict={sid:joint(row,'strict') for sid,row in a.to_dict('index').items()}
    new_strict={sid:joint(row,'strict') for sid,row in b.to_dict('index').items()}
    regional={sid for sid in a.index if bool(a.loc[sid,'centre_in_regional_roster'])}
    common={sid for sid in regional if old_joint[sid]!='unknown' and new_joint[sid]!='unknown'}
    numeric={sid for sid in common if new_strict[sid]!='unknown'}
    distribution=dict(sorted(Counter(new_joint[sid] for sid in numeric).items()))
    wanted={'current_np_records':len(old),'primary2010_applied_current_records':sum(applied.values()),
        'primary2010_changed_current_values':sum(applied[sid] and old.loc[sid,'population_2010']!=new.loc[sid,'population_2010'] for sid in old.index),
        'matched_np_same_complete_accepted_three_point_cohort':len(cohort),
        'matched_np_accepted_sequence_changes_in_same_cohort':sum(old_seq[sid]!=new_seq[sid] for sid in cohort),
        'regional_np_centres':len(regional),
        'baseline_regional_complete_numeric_primary_centre_rural_trajectories':sum(old_strict[sid]!='unknown' for sid in regional),
        'new_regional_complete_numeric_primary_centre_rural_trajectories':sum(new_strict[sid]!='unknown' for sid in regional),
        'regional_same_complete_accepted_centre_rural_cohort':len(common),
        'regional_accepted_centre_rural_trajectory_changes_same_cohort':sum(old_joint[sid]!=new_joint[sid] for sid in common),
        'regional_same_new_numeric_primary_complete_cohort':len(numeric),
        'regional_trajectory_changes_in_same_new_numeric_primary_complete_cohort':sum(old_joint[sid]!=new_joint[sid] for sid in numeric),
        'new_numeric_primary_cohort_reported_centre_rural_sequences':distribution}
    published=json.loads((comparison/'summary.json').read_text())
    for key,value in wanted.items():
        if published.get(key)!=value:errors.append('Published same-cohort comparison count differs '+key)
    wanted={key:int(value) if isinstance(value,(np.integer,np.bool_)) else value for key,value in wanted.items()}
    return {'schema':'sgrt.saratov.primary2010_same_cohort_independent.v1','independent_counts':wanted,'errors':errors,'violations':len(errors),
        'scope':'Same current NP-centre/member compositions, two2010reported-number sources. Component source sums and eligibility are checked separately; differences are not automatically legacy errors, imputation or causal demographic effects.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader',type=Path);parser.add_argument('--parsed',type=Path)
    parser.add_argument('--base-context',type=Path);parser.add_argument('--primary-context',type=Path);parser.add_argument('--comparison',type=Path)
    parser.add_argument('--evidence',type=Path);parser.add_argument('--population-long',type=Path)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    if a.comparison:
        if not a.base_context or not a.primary_context or not a.evidence:parser.error('Comparison audit requires bothcontexts and primaryevidence')
        result=compare_contexts(a.base_context,a.primary_context,a.evidence,a.comparison)
    else:
        if not a.reader:parser.error('Reader source required')
        result=audit(a.reader,a.parsed,a.evidence,a.population_long)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'municipal_checks','municipal_np_count_checks','independent_unparsed_type_anchors'}},ensure_ascii=False))
    if result['violations']:raise SystemExit('Independent2010audit failed')
