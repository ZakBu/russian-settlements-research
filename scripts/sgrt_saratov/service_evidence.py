"""Assess external service roles and compare documented school directions.

Consumes a few immutable v2 tables and the old native-road window, not a new
national simulation. No thresholds establish centres; missing supply stays
unknown. School admission boundaries are not observed pupil journeys.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape, mapping, LineString, box
from scripts.sgrt_zero.cloud_common_systems import acquire
from scripts.sgrt_saratov.country_scope import load_russia
from scripts.sgrt_saratov.source_inventory import BOUNDARY_URL
import urllib.request

PREFIX='sgrt/saratov-fields20261029-v2/results/'
BASIC=('school','medical_basic','grocery')
FOLDERS={'baseline':('functions','baseline_'),'documented':('functions',''),
         'preferred':('physical_official',''),'historical':('regional_supplement','')}
TAG='sgrt-saratov-service-evidence-20261103-v1'
REPO='ZakBu/russian-settlements-research'


def write(path, obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def live_edges(frame, scenario):
    f=frame[frame.evidence_scenario.eq(scenario)&frame.family.isin(BASIC)
        &frame.population_2021.gt(0)&frame.centre_id.notna()
        &frame.centre_id.ne(frame.origin_id)].copy()
    if f.duplicated(['centre_id','origin_id','family']).any():
        raise ValueError('External centre/origin/family membership is not unique')
    return f


def edge_set(frame):
    return set(frame[['centre_id','origin_id','family']].itertuples(index=False,name=None))


def compare_schools(links, assignments, roster, mask):
    axis=roster.set_index('source_record_id')
    rows=[];features=[]
    for r in assignments.itertuples(index=False):
        if pd.isna(r.origin_id):
            rows.append({'origin_name':r.origin_name_literal,'origin_id':None,
                'campus_name':r.campus_place_name,'campus_id':r.campus_id,
                'identity_status':r.identity_status,'scope':'identity_held'})
            continue
        pop=float(r.origin_population_2021) if pd.notna(r.origin_population_2021) else None
        scope='external_positive' if r.origin_id!=r.campus_id and pop is not None and pop>0 else 'self_positive' if r.origin_id==r.campus_id and pop is not None and pop>0 else 'zero_or_unknown_population'
        row={'origin_name':r.origin_name_literal,'origin_id':r.origin_id,
            'campus_name':r.campus_place_name,'campus_id':r.campus_id,
            'legal_parent_id':r.legal_parent_np_id,'scope':scope,
            'population_2021_not_pupil_count':pop,'document_year':2025,
            'document_assignment_is_observed_trip':False}
        for variant,l in links.items():
            found=l[l.origin_id.eq(r.origin_id)&l.family.eq('school')&l.evidence_scenario.eq('all_dated_known')]
            if len(found)!=1:raise ValueError('School outcome is not unique')
            f=found.iloc[0];keys=json.loads(f.coequal_primary_keys_json)
            row[variant+'_campus_match']='np:'+r.campus_id in keys
            row[variant+'_parent_match']='np:'+r.legal_parent_np_id in keys
            row[variant+'_nearest_known_np_ids_json']=json.dumps([k[3:] for k in keys if k.startswith('np:')])
            row[variant+'_minutes']=float(f.cost_minutes) if pd.notna(f.cost_minutes) else None
            row[variant+'_local_supply_known']=bool(f.known_local_supply)
        rows.append(row)
        if scope=='external_positive':
            a=axis.loc[r.origin_id];b=axis.loc[r.campus_id]
            if all(pd.notna(x) for x in [a.lon,a.lat,b.lon,b.lat]):
                line=LineString([(float(a.lon),float(a.lat)),(float(b.lon),float(b.lat))])
                # Administrative relation only, no invented route or boundary.
                if mask.covers(line):
                    features.append({'type':'Feature','geometry':mapping(line),'properties':{
                        'id':r.origin_id+'__documented_school','name':r.origin_name_literal+' → '+r.campus_place_name,
                        'class_index':0 if row['preferred_campus_match'] else 1,
                        'origin_id':r.origin_id,'campus_id':r.campus_id,
                        'preferred_nearest_matches_document':row['preferred_campus_match'],
                        'relation':'documented_admission_assignment_not_observed_journey',
                        'geometry_scope':'straight_relation_not_road_route','year':2025}})
    table=pd.DataFrame(rows);summary={}
    for scope in ['external_positive','self_positive','zero_or_unknown_population','identity_held']:
        s=table[table.scope.eq(scope)];record={'document_mentions':len(s)}
        for v in links:
            if scope=='identity_held':continue
            record[v+'_campus_matches']=int(s[v+'_campus_match'].sum())
            record[v+'_legal_parent_matches']=int(s[v+'_parent_match'].sum())
        summary[scope]=record
    summary['supply_locations_from_same_document_used_for_enrichment']=True
    summary['target_assignment_not_used_to_force_destinations']=True
    summary['is_new_independent_holdout_validation']=False
    summary['all_documented_records']=len(table)
    return table,summary,{'type':'FeatureCollection','features':features}


def build(work):
    work=Path(work);work.mkdir(parents=True,exist_ok=True);source=work/'input';out=work/'results';out.mkdir(exist_ok=True)
    required={PREFIX+'fields/regional_roster.parquet',PREFIX+'physical_official/loss_counterfactual.parquet',
        PREFIX+'context_physical_official/basic_centre_economic_context.parquet'}
    for folder,prefix in FOLDERS.values():
        for name in ['functional_system_members','basic_centre_profiles','functional_links']:
            required.add(PREFIX+folder+'/'+prefix+name+'.parquet')
    provenance=acquire(Path('data/saratov_fields_catalog_20261029_v2.json'),lambda p:p in required,source,work/'cache')
    def table(name):return pd.read_parquet(source/PREFIX/name)
    roster=table('fields/regional_roster.parquet')
    members={k:table(folder+'/'+prefix+'functional_system_members.parquet') for k,(folder,prefix) in FOLDERS.items()}
    profiles={k:table(folder+'/'+prefix+'basic_centre_profiles.parquet') for k,(folder,prefix) in FOLDERS.items()}
    links={k:table(folder+'/'+prefix+'functional_links.parquet') for k,(folder,prefix) in FOLDERS.items()}
    base=profiles['preferred'];base=base[base.evidence_scenario.eq('all_dated_known')&base.centre_in_regional_roster].copy()
    if len(base)!=511 or base.centre_id.duplicated().any():raise ValueError('Preferred candidate axis differs from the published v2')
    preferred=live_edges(members['preferred'],'all_dated_known')
    inventories={k:live_edges(m,'all_dated_known') for k,m in members.items()}
    inventories['preferred_nonhistorical']=live_edges(members['preferred'],'nonhistorical_evidence_only')
    sets={k:edge_set(m) for k,m in inventories.items()}
    stats=[];sensitive={}
    for label,edges in inventories.items():
        regional=set(edges.centre_id)&set(roster.source_record_id)
        diff=sets['preferred']^sets[label]
        sensitive[label]={'regional_candidates':len(regional),
            'preferred_candidates_retained':len(set(base.centre_id)&regional),
            'preferred_direct_basic_edges':len(sets['preferred']),
            'common_direct_basic_edges':len(sets['preferred']&sets[label]),
            'symmetric_edge_difference':len(diff),
            'preferred_edge_retention_fraction':len(sets['preferred']&sets[label])/len(sets['preferred'])}
    loss=table('physical_official/loss_counterfactual.parquet')
    loss=loss[loss.evidence_scenario.eq('all_dated_known')&loss.family.isin(BASIC)&loss.population_2021_published.gt(0)
        &loss.origin_distinct_from_known_centre.eq(True)&loss.removed_centre_id.isin(base.centre_id)]
    if loss.duplicated(['removed_centre_id','origin_id','family']).any():raise ValueError('Repeated loss outcome')
    if loss.additional_minutes.dropna().lt(-1e-7).any():raise ValueError('Removal improves travel time')
    for r in base.itertuples(index=False):
        e=preferred[preferred.centre_id.eq(r.centre_id)]
        support=e.groupby('origin_id').family.nunique()
        row={'centre_id':r.centre_id,'name':r.centre_name,'population_2021':float(r.centre_population_2021) if pd.notna(r.centre_population_2021) else None,
            'known_own_basic_function_count':int(r.known_own_basic_function_count),
            'external_inhabited_origins':int(e.origin_id.nunique()),
            'origins_same_centre_at_least_two_functions':int(support.ge(2).sum()),
            'origins_same_centre_three_functions':int(support.eq(3).sum()),
            'independently_established_centre':None,'observed_trips_established':False}
        for label,es in sets.items():
            original={v for v in sets['preferred'] if v[0]==r.centre_id}
            retained=original&es
            row[label+'_retained_direct_edges']=len(retained)
            row[label+'_retained_external_origins']=len({v[1] for v in retained})
            row[label+'_all_preferred_direct_edges_retained']=bool(original<=es)
        for f in BASIC:
            l=loss[loss.removed_centre_id.eq(r.centre_id)&loss.family.eq(f)]
            vals=l.additional_minutes.dropna()
            row[f+'_external_origins']=int(e[e.family.eq(f)].origin_id.nunique())
            row[f+'_loss_finite_origin_count']=int(len(vals))
            row[f+'_loss_additional_minutes_median']=float(vals.median()) if len(vals) else None
            row[f+'_loss_additional_minutes_max']=float(vals.max()) if len(vals) else None
            row[f+'_loss_alternative_time_unknown_count']=int(l.additional_minutes.isna().sum())
            row[f+'_loss_unresolved_alternative_np_count']=int(l.alternative_np_identity_unresolved.eq(True).sum())
        stats.append(row)
    candidates=pd.DataFrame(stats)
    boundary=work/'RUS-adm1.geojson'
    with urllib.request.urlopen(BOUNDARY_URL,timeout=60) as response:boundary.write_bytes(response.read())
    mask=load_russia(boundary)
    assignments=pd.read_csv('sgrt/saratov/documented_school_catchments_2025.csv')
    school,school_summary,school_geo=compare_schools(links,assignments,roster,mask)
    road_path='sgrt/saratov-isochrones20261028/results/model/native_edges.parquet'
    road_provenance=acquire(Path('data/saratov_isochrones_catalog_20261028.json'),lambda p:p==road_path,source,work/'cache')
    native=pd.read_parquet(source/road_path)
    geometries=shapely.from_wkb(native.native_geometry_wkb.to_numpy())
    bounds=shapely.total_bounds(geometries)
    local_mask=shapely.intersection(mask,box(bounds[0]-1,bounds[1]-1,bounds[2]+1,bounds[3]+1))
    inside=shapely.covered_by(geometries,local_mask)
    road_summary={'native_road_segments':len(native),'entirely_in_pinned_russian_outline':int(inside.sum()),
        'segments_not_entirely_in_outline':int((~inside).sum()),'schema':list(native.columns),
        'scope':'Only saved native road segments within the old six-centre 60-minute display/search window; not all national or 480-minute paths.',
        'foreign_transit_of_all_v2_routes_certified':False}
    economic=table('context_physical_official/basic_centre_economic_context.parquet')
    summary={'schema':'sgrt.saratov.service_evidence.20261103.v1','candidate_count':len(candidates),
        'inventory_sensitivity':sensitive,
        'all_preferred_edges_retained_without_historical_only':int(candidates.preferred_nonhistorical_all_preferred_direct_edges_retained.sum()),
        'at_least_one_external_origin_two_functions':int(candidates.origins_same_centre_at_least_two_functions.gt(0).sum()),
        'at_least_one_external_origin_three_functions':int(candidates.origins_same_centre_three_functions.gt(0).sum()),
        'school_assignment_comparison':school_summary,'native_road_window_country_screen':road_summary,
        'economic_context_schema':list(economic.columns),
        'limitations':['No candidate count becomes a confirmed-centre count.',
            'Past cost tables are retained; this calculation does not certify no foreign transit.',
            'All-resident population is not pupils, patients, employed residents or trip counts.',
            'Counterfactuals remove all known offers of one function in a destination NP; they do not predict actual closures.',
            'Absence from or sensitivity to an inventory does not prove absence of local supply.']}
    for col in economic.columns:
        if pd.api.types.is_numeric_dtype(economic[col]) and not pd.api.types.is_bool_dtype(economic[col]):
            summary.setdefault('economic_numeric_known_rows',{})[col]=int(economic[col].notna().sum())
    for name,frame in [('candidate_role_vectors',candidates),('school_assignment_comparison',school),('candidate_economic_context',economic)]:
        frame.to_parquet(out/(name+'.parquet'),index=False,compression='zstd')
        frame.to_csv(out/(name+'.csv'),index=False)
    write(out/'school_documented_relations.geojson',school_geo)
    write(out/'summary.json',summary)
    write(out/'input_provenance.json',provenance+road_provenance)
    # Keep a compact inspectable set of disagreements and largest model losses.
    external=school[school.scope.eq('external_positive')]
    mismatch=external[external.preferred_campus_match.eq(False)]
    examples={'school_external_mismatches':json.loads(mismatch.to_json(orient='records')),
        'largest_model_school_loss':json.loads(candidates.sort_values('school_loss_additional_minutes_median',ascending=False).head(15).to_json(orient='records')),
        'source':'Archived v2 and documented 2025 admission assignments; model, not actual flows.'}
    write(out/'examples.json',examples)
    return out,summary,examples


def publish(out,summary,examples):
    producer=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    archive=out.parent/'saratov-service-evidence.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.iterdir()):z.write(p,'saratov-service-evidence/'+p.name)
    files=[archive,out/'school_documented_relations.geojson']
    manifest={'release':TAG,'source_commit':producer,'assets':[]}
    for p in files:
        manifest['assets'].append({'asset':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'url':f'https://github.com/{REPO}/releases/download/{TAG}/'+p.name})
    write(out.parent/'manifest.json',manifest)
    subprocess.run(['gh','release','create',TAG,'--repo',REPO,'--target',producer,
        '--title','Саратов: внешнее обслуживание, альтернативы и проверка школьных направлений',
        '--notes','Предварительная проверка роли кандидатов по неизменным данным v2. Не новые наблюдённые потоки и не утверждённое районирование.',
        *map(str,files),str(out.parent/'manifest.json')],check=True)
    for a in manifest['assets']:
        with urllib.request.urlopen(a['url'],timeout=60) as response:raw=response.read()
        if hashlib.sha256(raw).hexdigest()!=a['sha256']:raise ValueError('Public scientific asset differs')
    write('research_context/analysis_snapshots/saratov_service_evidence_20261103.json',summary)
    write('research_context/analysis_snapshots/saratov_service_examples_20261103.json',examples)
    write('research_context/analysis_snapshots/saratov_service_manifest_20261103.json',manifest)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--publish',action='store_true')
    args=parser.parse_args();out,summary,examples=build(args.work)
    if args.publish:publish(out,summary,examples)
    else:print(json.dumps(summary,ensure_ascii=False,indent=2))
