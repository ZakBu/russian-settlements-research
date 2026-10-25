#!/usr/bin/env python3
"""Read-only semantic counterexample search in a restored public result.

No provider eligibility or address identity is changed. Diagnostic categories
distinguish incompatible functions, conflicting physical roles, explicit access
conditions and declared uncertainty about programmes or admission.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import pandas as pd

FAMILIES=('school_general','preschool','vocational_education','higher_education')
LOOKALIKE=str.maketrans({'a':'а','A':'А','c':'с','C':'С','e':'е','E':'Е',
    'o':'о','O':'О','p':'р','P':'Р','x':'х','X':'Х','y':'у','Y':'У',
    'k':'к','K':'К','m':'м','M':'М','t':'т','T':'Т','B':'В','H':'Н'})


def semantic_name(value):
    original='' if value is None or pd.isna(value) else str(value)
    def fold(match):
        token=match.group()
        latin=re.findall('[A-Za-z]',token)
        return token.translate(LOOKALIKE) if latin and all(ord(x) in LOOKALIKE for x in latin) and re.search('[А-Яа-яЁё]',token) else token
    return re.sub('[A-Za-zА-Яа-яЁё]+',fold,original).lower().replace('ё','е')


def flags(row,tags):
    name=semantic_name(row['name']);family=row['service_code'];out=[]
    general=bool(re.search(r'общеобразовательн|\b(?:сош|оош|нош)\b|гимнази|\bлицей\b',name))
    art=bool(re.search(r'школ\w*\s+(?:[а-я-]+\s+){0,3}(?:искусств|искуств)|\b(?:дши|дмш|дхш)\b|музыкальн\w*\s+школ|художественн\w*\s+школ',name))
    preschool_label=bool(re.search(r'детск\w*\s+сад|ясли|дошкольн|д[/\\]с\b',name))
    if art and not general:
        degree_context=bool(re.search(r'высш|колледж|училищ|университет|институт|академи|консерватори',name))
        child=bool(re.search(r'детск\w*\s+(?:[а-я-]+\s+){0,3}школ|\b(?:дши|дмш|дхш)\b',name))
        if family=='preschool' and preschool_label:
            out.append(('co_located_preschool_and_arts','positive_mixed_programme_not_automatic_error'))
        else:
            out.append(('incompatible_supplementary_arts','clear_function_counterexample') if child or not degree_context else
                       ('arts_school_with_degree_context','requires_programme_review_not_automatic_error'))
    degree_context=bool(re.search(r'высш|колледж|училищ|университет|институт|академи|консерватори',name))
    if not general and not degree_context and re.search(r'спорт\s*школ|спортивн\w*\s+школ|\b(?:дюсш|сшор|сдюшор)\b|школ\w*\s+олимпийского\s+резерва|автошкол|школ\w*\s+вождени|школ\w*\s+(?:английского|немецкого|французского|китайского|иностранных\s+языков)',name):
        out.append(('other_explicit_supplementary_programme','clear_function_counterexample'))
    if re.search(r'общежити|\bdormitor',name):
        out.append(('named_dormitory','physical_role_counterexample'))
    elif str(tags.get('building','')).lower()=='dormitory':
        out.append(('dormitory_building_tag','conflicting_source_roles_requires_review'))
    if re.search(r'^спортзал|^столовая|^котельн|^прачечн|^гараж|^ректорат|^библиотек|административн\w*\s+корпус',name):
        out.append(('named_ancillary_facility','physical_role_counterexample'))
    if re.search(r'не\s+работает|закрыт[аоы]?(?:\b|\s)|бывш\w*\s+школ',name):
        out.append(('name_reports_inactive_or_former','conflicting_source_roles_requires_review'))
    inactive={k:str(v) for k,v in tags.items() if k in {'abandoned:building','disused:building','demolished:building'} and str(v).lower()=='yes'}
    if inactive:out.append(('inactive_building_tag','conflicting_source_roles_requires_review'))
    if str(tags.get('building','')).lower() in {'construction','ruins'} or any(k.startswith(('construction:','proposed:')) and k.endswith('amenity') for k in tags):
        out.append(('construction_ruins_or_proposed_role','conflicting_source_roles_requires_review'))
    access=str(tags.get('access','')).lower()
    if access in {'no','private','delivery','military','permit','customers'}:
        out.append(('explicit_access_'+access,'source_access_condition_not_modelled'))
    if family in {'vocational_education','higher_education'} and re.search(r'\bдпо\b|переподготовк|повышени\w*\s+квалификаци|курсы\s+(?:подготовки|повышения)',name):
        out.append(('named_continuing_training','degree_function_not_established'))
    if family=='school_general':
        if re.search(r'(?<![а-яa-z0-9])(?:viii|vii|vi|iv|iii|ii|i|v|[1-8])\s*[-‑–]?\s*(?:го|ого|й)?\s*вида|\bспец\.\s*корр\.',name):
            out.append(('coded_special_school_programme','specific_programme_not_universal_daytime'))
        # An upper-secondary-only literal does not prove primary schooling.
        # The published generic-school channel explicitly disclaims stage
        # eligibility; this is a scale-of-limitation readout, not a new error.
        programme=json.loads(row.get('school_program_evidence_json') or '{}')
        levels=set(programme.get('isced_levels',[]));grades=set(programme.get('grades_list',[]))
        if (levels and not levels&{1,2} and 3 in levels) or (grades and min(grades)>=10):
            out.append(('literal_upper_secondary_only','declared_generic_stage_limitation'))
    if str(tags.get('operator:type','')).lower().startswith('private'):
        out.append(('private_operator','declared_admission_uncertainty_not_function_error'))
    return out


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(bundle,output):
    bundle=Path(bundle);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    sites_path=bundle/'education/physical_sites.parquet';sites=pd.read_parquet(sites_path)
    sources=[sites_path];diagnostics=[]
    for row in sites.loc[sites.eligible.eq(True)].to_dict('records'):
        tags=json.loads(row['tags_json'])
        for category,interpretation in flags(row,tags):
            diagnostics.append({k:row.get(k) for k in ['provider_id','source_record_id','name','service_code','region','site_lat','site_lon','tags_json','education_need_scope','school_program_evidence_json']}|
                {'category':category,'interpretation':interpretation,'semantic_name':semantic_name(row['name']),
                 'mixed_script_name_changed':semantic_name(row['name'])!=('' if row['name'] is None or pd.isna(row['name']) else str(row['name']).lower().replace('ё','е'))})
    diagnosed=pd.DataFrame(diagnostics)
    route_counts=[];route_examples=[];all_routes=[]
    for family in FAMILIES:
        path=bundle/'routes/nearest'/f'{family}.parquet';sources.append(path)
        route=pd.read_parquet(path,columns=['origin_id','name','region','population','selected_provider_id','cost_minutes','known_local_supply','point_separation_km'])
        route['service_code']=family;route['inhabited']=pd.to_numeric(route.population,errors='coerce').gt(0)
        all_routes.append(route)
        counts=route.groupby('selected_provider_id',dropna=False).agg(selected_origin_records=('origin_id','nunique'),
            selected_inhabited_origins=('inhabited','sum'),local_selected_origins=('known_local_supply','sum'),
            minimum_cost_minutes=('cost_minutes','min'),maximum_cost_minutes=('cost_minutes','max')).reset_index().rename(columns={'selected_provider_id':'provider_id'})
        counts['service_code']=family;route_counts.append(counts)
    counts=pd.concat(route_counts,ignore_index=True)
    diagnosed=diagnosed.merge(counts,on=['service_code','provider_id'],how='left',validate='many_to_one')
    for c in ['selected_origin_records','selected_inhabited_origins','local_selected_origins']:
        diagnosed[c]=diagnosed[c].fillna(0).astype(int)
    edge_path=bundle/'screens_final/daily_edges.parquet';sources.append(edge_path)
    edges=pd.read_parquet(edge_path,columns=['scenario_id','service_family','provider_site_id','origin_id','l0_admitted','origin_positive_population'])
    edges=edges[edges.scenario_id.eq('daily_20_school30_wb')&edges.service_family.eq('school')&edges.l0_admitted]
    admitted=edges.groupby('provider_site_id').agg(main_l0_admitted_origins=('origin_id','nunique'),main_l0_admitted_inhabited_origins=('origin_positive_population','sum')).reset_index().rename(columns={'provider_site_id':'provider_id'})
    diagnosed=diagnosed.merge(admitted,on='provider_id',how='left',validate='many_to_one')
    for c in ['main_l0_admitted_origins','main_l0_admitted_inhabited_origins']:diagnosed[c]=diagnosed[c].fillna(0).astype(int)
    diagnosed.to_parquet(output/'eligible_feature_diagnostics.parquet',index=False)
    diagnosed.sort_values(['interpretation','selected_origin_records'],ascending=[True,False]).to_csv(output/'eligible_feature_diagnostics.csv',index=False)
    selected=diagnosed[diagnosed.selected_origin_records.gt(0)]
    selected.to_parquet(output/'selected_feature_diagnostics.parquet',index=False)
    selected.to_csv(output/'selected_feature_diagnostics.csv',index=False)
    routes=pd.concat(all_routes,ignore_index=True)
    witnesses=routes.merge(selected[['provider_id','service_code','category','interpretation']],left_on=['selected_provider_id','service_code'],right_on=['provider_id','service_code'],how='inner',validate='many_to_many')
    witnesses.to_parquet(output/'routes_to_flagged_points.parquet',index=False)
    groups=[]
    for (family,category,interpretation),g in diagnosed.groupby(['service_code','category','interpretation']):
        w=witnesses[witnesses.service_code.eq(family)&witnesses.category.eq(category)]
        groups.append({'service_code':family,'category':category,'interpretation':interpretation,
            'eligible_site_count':g.provider_id.nunique(),'selected_site_count':g.loc[g.selected_origin_records.gt(0),'provider_id'].nunique(),
            'raw_affected_origin_records':w.origin_id.nunique(),'raw_affected_inhabited_origins':w.loc[w.inhabited,'origin_id'].nunique(),
            'main_l0_admitted_origins':int(g.main_l0_admitted_origins.sum()),
            'main_l0_admitted_inhabited_origins':int(g.main_l0_admitted_inhabited_origins.sum())})
    summary={'scope':'Public frozen result, diagnostic only; source classifier and assignments unchanged',
        'eligible_education_features':int(sites.eligible.sum()),'diagnostic_rows':len(diagnosed),
        'category_counts_are_overlapping_not_additive':True,'groups':groups,
        'input_sha256':{str(p):sha(p) for p in sources},'diagnostic_code_sha256':sha(__file__)}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.bundle,a.output)
