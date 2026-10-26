"""Rebuild exploratory scale and conditional cooperation from immutable public bytes.

This release contains no claimed new empirical SGRT/agglomeration ranks. Every
Parquet column and row is compared to an independent completed local calculation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import pandas as pd
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_zero.cloud_common_systems import (acquire, clean_commit, link_or_copy,
    releases, run, sha, verify, write, REPOSITORY)
from scripts.sgrt_zero.identity_control import table_hash
from scripts.sgrt_zero.municipal_workforce_source import MEMBER, MEMBER_BYTES, MEMBER_SHA256
from scripts.sgrt_mass.routes import GRAPH_SHA256
TAG = 'sgrt-upper-research-20261027-v1'
PREFIX = 'sgrt/upper20261027/'
EXPECTED = REPO/'research_context/analysis_snapshots/upper_research_control_20261027.json'
Z = 'sgrt/zero20261025/'
I = 'sgrt/identity20261026/'
C = 'sgrt/common20261027/'
G = 'research/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2/'
INPUTS = {
 'data/zero_catalog_20261025.json': [Z+'context/analysis_reference.parquet',
    Z+'federal_medical/addresses/F038_current_np_identity.parquet',
    Z+'federal_medical/functions/service_evidence_by_care_address.parquet',
    Z+'literature/external_fua_russia/russia_efua_2015.parquet',
    Z+'literature/external_fua_russia/settlement_external_fua_status.parquet'],
 'data/identity_catalog_20261026.json': [I+'routes/endpoint_network_quality.parquet',
    I+'routes/sources/education/physical_sites.parquet', I+'routes/sources/commerce/sites.parquet',
    I+'registry/level0_centres.csv', I+'registry/level0_memberships.parquet'],
 'data/mass_catalog_20261024.json': ['sgrt/mass20261024/context/settlement_context.parquet'],
 'data/common_systems_catalog_20261027.json': [C+'results/level0/units.parquet', C+'results/level0/memberships.parquet'],
 'data/catalog.json': [G+'graph_npz_parts/part_'+str(n).zfill(3)+'.bin' for n in range(3)],
}


def scientific_summary(value):
    """Compare scientific diagnostics, excluding paths, retrieval mode and code bytes."""
    excluded = {'input_sha256','inputs_sha256','code_sha256','implementation_sha256','retrieval'}
    if isinstance(value,dict):return {k:scientific_summary(v) for k,v in value.items() if k not in excluded}
    if isinstance(value,list):return [scientific_summary(v) for v in value]
    if isinstance(value,float):return round(value,6)
    return value


def control(results):
    tables = {}
    for path in sorted(Path(results).rglob('*.parquet')):
        frame = pd.read_parquet(path)
        tables[path.relative_to(results).as_posix()] = table_hash(frame, list(frame.columns))
    if not tables: raise ValueError('No complete scientific output tables')
    maps = {}
    for filename in ['municipal-scale-points.csv','conditional-cooperation-60-points.csv']:
        path = Path(results)/filename
        if not path.is_file(): raise ValueError('Site exports must be generated before freezing control')
        frame = pd.read_csv(path)
        maps[filename] = table_hash(frame, list(frame.columns))
    summaries = {}
    for filename in ['np_diagnostic/summary.json','municipal/summary.json','roads/road_summary.json','potential/gravity_summary.json','cooperation/urban_cooperation_summary.json','workforce/source_facts.json']:
        path = Path(results)/filename
        if path.is_file(): summaries[filename] = scientific_summary(json.loads(path.read_text()))
    census_tables = {}
    census_json = {}
    for path in sorted((Path(results)/'census_workplace').glob('*.csv')):
        frame = pd.read_csv(path)
        census_tables[path.name] = table_hash(frame, list(frame.columns))
    for path in sorted((Path(results)/'census_workplace').glob('*.json')):
        value = json.loads(path.read_text())
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        census_json[path.name] = {'canonical_json_sha256':hashlib.sha256(encoded).hexdigest(),
            'top_level_records':len(value), 'every_key_value_and_list_item_compared':True}
    return {'schema':'sgrt.upper_research_control.v1', 'census_tables':census_tables, 'census_json':census_json, 'scientific_summaries':summaries, 'tables':tables, 'map_tables':maps,
        'map_scope':json.loads((Path(results)/'map_scope.json').read_text()),
        'numeric_comparison_decimal_places':8, 'summary_numeric_comparison_decimal_places':6, 'row_multiplicity_and_every_column_compared':True,
        'empirical_hierarchy_established':False}


def site_exports(results, reference):
    """Map territorial totals only at explicitly labelled representative NP points."""
    results = Path(results)
    ref = pd.read_parquet(reference)
    profiles = pd.read_parquet(results/'municipal/municipal_scale_comparisons.parquet')
    cross = pd.read_parquet(results/'municipal/reference_parent_crosswalk.parquet')
    required = {'source_record_id','name','lat','lon','population_2021','credit_2021','ordinary_spatial_2021'}
    if not required <= set(ref): raise ValueError('Representative point fields missing')
    valid = ref[ref.lat.between(-90,90) & ref.lon.between(-180,180) & ref.credit_2021.eq(True) & ref.ordinary_spatial_2021.eq(True)].merge(
        cross, on='source_record_id', validate='one_to_one')
    # Population chooses a label point, never redistributes municipal workers.
    points = valid.sort_values(['population_2021','source_record_id'], ascending=[False,True], kind='stable').drop_duplicates('matched_2021_parent_code')
    p = profiles[profiles.recorded_component_comparison_eligible.eq(True)].merge(
        points[['matched_2021_parent_code','source_record_id','name','lat','lon']], left_on='oktmo',
        right_on='matched_2021_parent_code', how='left', validate='one_to_one')
    # Federal cities are whole subjects and have no synthetic common parent.
    for code,name in [('45000000','Москва'),('40000000','Санкт-Петербург')]:
        city = ref[ref.name.eq(name)].sort_values('population_2021', ascending=False)
        if city.empty: raise ValueError('Federal-city representative absent')
        for field in ['name','lat','lon','source_record_id']: p.loc[p.oktmo.eq(code),field] = city.iloc[0][field]
    p = p.dropna(subset=['lat','lon']).copy()
    p['name'] = p.municipality.astype(str)+' — частичная численность работников МО, 2025; точка: '+p['name'].astype(str)
    p['value'] = p.partial_organisation_workers_2025_territorial
    p['point_scope'] = 'representative_settlement_point_of_recorded_municipal_territory_not_worker_location'
    p[['name','lat','lon','value','oktmo','source_record_id','point_scope']].to_csv(results/'municipal-scale-points.csv',index=False)
    links = pd.read_parquet(results/'cooperation/urban_cooperation_candidates.parquet')
    links = links[links.time_budget_scenario_minutes.eq(60) & links.spatial_time_admissible.eq(True)].copy()
    links['name'] = links.core_name
    links['lat'] = links.core_lat
    links['lon'] = links.core_lon
    links['value'] = links.conditional_cooperation_link_with_territorial_scale_evidence.map({True:1,False:2})
    links['name'] = links['name']+' → '+links.parent_name+'; условный кандидат, сценарий 60 мин'
    links[['name','lat','lon','value','unit_id','parent_origin_id']].to_csv(results/'conditional-cooperation-60-points.csv',index=False)
    for filename in ['municipal-scale-points.csv','conditional-cooperation-60-points.csv']:
        frame = pd.read_csv(results/filename)
        if frame[['lat','lon','value']].isna().any().any(): raise ValueError('Map coordinates or values missing')
        if not frame.lat.between(-90,90).all() or not frame.lon.between(-180,180).all(): raise ValueError('Invalid map coordinates')
    write(results/'map_scope.json',{'municipal_map_points':len(p),
        'complete_comparison_territories':int(profiles.recorded_component_comparison_eligible.sum()),
        'conditional_60_minute_points':len(links),'municipal_workers_assigned_to_np':False,
        'continuous_municipal_values':True,'cooperation_categories':{'1':'spatial-time admissible and distinct municipal recorded-component dominance','2':'spatial-time admissible; functional rank unidentified'},
        'observed_flows_or_verified_agglomerations':False})


def calculate(source, results):
    results.mkdir(parents=True,exist_ok=True)
    ref=source/Z/'context/analysis_reference.parquet'
    med=source/Z/'federal_medical/functions/service_evidence_by_care_address.parquet'
    addr=source/Z/'federal_medical/addresses/F038_current_np_identity.parquet'
    context=source/'sgrt/mass20261024/context/settlement_context.parquet'
    run('scripts/sgrt_zero/census_workplace_evidence.py','--input-dir',REPO/'references/primary/census_workplace_20261027',
        '--output-dir',results/'census_workplace','--population-reference',ref)
    run('scripts/sgrt_zero/municipal_workforce_source.py','--output',results/'workforce')
    run('scripts/sgrt_zero/centrality_profiles.py','--reference',ref,'--medical-evidence',med,
        '--medical-addresses',addr,'--education',source/I/'routes/sources/education/physical_sites.parquet',
        '--commerce',source/I/'routes/sources/commerce/sites.parquet','--workforce',context,
        '--max-k','10','--bootstrap-repeats','3','--output',results/'np_diagnostic')
    run('scripts/sgrt_zero/municipal_centrality_profiles.py','--workforce',results/'workforce'/MEMBER,
        '--reference',ref,'--parent-context',context,'--medical-profiles',results/'np_diagnostic/centrality_profiles.parquet',
        '--medical-evidence',med,'--medical-addresses',addr,'--output',results/'municipal')
    run('scripts/sgrt_zero/hierarchy_gravity_candidates.py','road-costs','--reference',ref,
        '--endpoints',source/I/'routes/endpoint_network_quality.parquet','--graph-directory',source/G,
        '--coordinate-holds',REPO/'references/provenance/coordinate_holds_20261026.json',
        '--network-limit','180','--output',results/'roads')
    run('scripts/sgrt_zero/gravity_pilot_sensitivity.py','--profiles',results/'np_diagnostic/centrality_profiles.parquet',
        '--pairs',results/'roads/pilot_current_city_costs.parquet','--centres',source/I/'registry/level0_centres.csv',
        '--half-lives','10','20','30','--transforms','linear','log1p','--output',results/'potential')
    run('scripts/sgrt_zero/urban_cooperation_candidates.py','--reference',ref,
        '--memberships',source/C/'results/level0/memberships.parquet','--units',source/C/'results/level0/units.parquet',
        '--service-memberships',source/I/'registry/level0_memberships.parquet',
        '--pairs',results/'roads/pilot_current_city_costs.parquet','--polygons',source/Z/'literature/external_fua_russia/russia_efua_2015.parquet',
        '--efua-status',source/Z/'literature/external_fua_russia/settlement_external_fua_status.parquet',
        '--parent-crosswalk',results/'municipal/reference_parent_crosswalk.parquet',
        '--municipal-profiles',results/'municipal/municipal_scale_comparisons.parquet',
        '--time-budgets','30','60','90','--output',results/'cooperation')
    verify(results/'workforce'/MEMBER,{'bytes':MEMBER_BYTES,'sha256':MEMBER_SHA256})
    site_exports(results,ref)


def package(results,built,commit,proof,actual):
    if built.exists(): raise ValueError('Output package must be new')
    built.mkdir(parents=True)
    entries={'results/'+p.relative_to(results).as_posix():p for p in results.rglob('*') if p.is_file()}
    context=['AGENTS.md','docs/UPPER_RESEARCH_RELEASE.md','decisions.json','research_context/current_state.json',
        'research_context/primary/word_concept_extracted.txt','references/provenance/municipal_workforce_20261027.json',
        'references/provenance/coordinate_holds_20261026.json','references/provenance/census_workplace_20261027.json','.github/workflows/publish-upper-research.yml',
        'requirements-upper-research.txt',EXPECTED.relative_to(REPO).as_posix(),*INPUTS]
    context += [p.relative_to(REPO).as_posix() for folder in ['scripts/sgrt_zero','scripts/sgrt_mass','scripts/sgrt_pilot'] for p in (REPO/folder).glob('*.py')]
    context += ['scripts/research_data.py']
    context += [p.relative_to(REPO).as_posix() for p in (REPO/'references/primary/census_workplace_20261027').glob('*.md')]
    if len([name for name in context if name.startswith('references/primary/census_workplace_20261027/')]) != 6:
        raise ValueError('All six pinned primary census renderings must be bundled')
    context += [p.relative_to(REPO).as_posix() for p in (REPO/'tests').glob('test_sgrt_zero_*.py')]
    for name in sorted(set(context)):
        path=REPO/name
        if not path.is_file(): raise FileNotFoundError(path)
        entries['reproduction/'+name]=path
    assets=[]
    for name in ['municipal-scale-points.csv','conditional-cooperation-60-points.csv']:
        if (results/name).stat().st_size > 20_000_000: raise ValueError('Map CSV exceeds existing editor adapter size limit')
        target=built/name;link_or_copy(results/name,target);assets.append(target)
    manifest={'schema':'sgrt.upper_research_bundle.v1','source_commit':commit,'release_tag':TAG,
        'archive_root':PREFIX,'input_provenance':proof,
        'new_workforce_source':json.loads((results/'workforce/source_facts.json').read_text()),'graph_csr_sha256_verified_by_loader':GRAPH_SHA256,
        'semantic_control':actual,'scientific_scope':'Recorded scale diagnostics, six-city road sensitivity and conditional cooperation candidates; no observed flows or empirical hierarchy.',
        'empirical_sgrt_or_agglomeration_levels_established':False,
        'files':{name:{'bytes':p.stat().st_size,'sha256':sha(p)} for name,p in sorted(entries.items())},
        'standalone_assets':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in assets}}
    archive=built/'upper-research.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
        for name,path in sorted(entries.items()):z.write(path,PREFIX+name)
        z.writestr(PREFIX+'bundle_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    manifest['archive']={'asset':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive)}
    write(built/'manifest.json',manifest)
    (built/'release_notes.md').write_text('Записанный масштаб территорий, дорожные сценарии шести городов и условные кандидаты кооперации.\n\nНовые эмпирические уровни СГРТ не установлены. Муниципальная численность работников не распределена по населённым пунктам. Внешние eFUA 2015 задают условный контур, не проверяют модель независимо. Полные таблицы, сырой источник работников, код и происхождение входов включены в ZIP.\n')
    return built


def publish(built,commit):
    clean_commit(commit)
    manifest=json.loads((built/'manifest.json').read_text())
    if manifest['source_commit']!=commit or manifest['release_tag']!=TAG: raise ValueError('Producer/tag mismatch')
    assets=[built/manifest['archive']['asset'],built/'manifest.json']
    verify(assets[0],manifest['archive'])
    for name,spec in manifest['standalone_assets'].items():
        path=built/name;verify(path,spec);assets.append(path)
    if any(r.get('tag_name')==TAG for r in releases()):raise ValueError('Existing releases and drafts must never be overwritten')
    tag=subprocess.run(['gh','api',f'repos/{REPOSITORY}/git/ref/tags/{TAG}'],capture_output=True,text=True)
    if tag.returncode==0 or 'HTTP 404' not in tag.stderr:raise ValueError('Publication tag absence unproven')
    subprocess.run(['gh','release','create',TAG,'--repo',REPOSITORY,'--target',commit,'--draft',
        '--title','Масштаб территорий и условная кооперация: 27 октября 2026','--notes-file',str(built/'release_notes.md'),*map(str,assets)],check=True)
    matches=[r for r in releases() if r.get('tag_name')==TAG and r.get('draft') is True]
    if len(matches)!=1:raise ValueError('Exactly one created draft required')
    release=matches[0]
    expected={p.name:(p.stat().st_size,'sha256:'+sha(p)) for p in assets}
    if release.get('target_commitish')!=commit or len(release.get('assets',[]))!=len(expected) or {a['name']:(a['size'],a.get('digest')) for a in release.get('assets',[])}!=expected:
        raise ValueError('Draft producer/asset digests differ; retained unpublished')
    # Root independently reviews this concrete draft before public release.
    # Never expose it automatically from the producer workflow.
    return {'draft_release_id':release['id'], 'draft':True,
        'requires_root_verification_before_publication':True}


def build(work,commit):
    clean_commit(commit)
    if work.exists() or work.resolve().is_relative_to(REPO):raise ValueError('New workspace outside Git required')
    if not EXPECTED.is_file():raise ValueError('Independent local control is required')
    proof=[];source=work/'input';source.mkdir(parents=True)
    for catalog,names in INPUTS.items():
        available={r['path'] for r in json.loads((REPO/catalog).read_text())['files']}
        if set(names)-available:raise ValueError('Pinned inputs absent: '+str(set(names)-available))
        proof+=acquire(REPO/catalog,lambda path:path in names,source,work/'cache')
    write(work/'source_facts.json',proof)
    results=work/'results';calculate(source,results)
    actual=control(results);write(work/'actual_control.json',actual)
    if actual!=json.loads(EXPECTED.read_text()):raise ValueError('Independent complete-table control differs; publication blocked')
    return package(results,work/'built',commit,proof,actual)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-commit');p.add_argument('--workdir',type=Path);p.add_argument('--publish-built',type=Path)
    p.add_argument('--control-results',type=Path);p.add_argument('--control-output',type=Path)
    args=p.parse_args()
    if args.control_results:
        if not args.control_output:p.error('--control-output required')
        write(args.control_output,control(args.control_results));return
    if not args.source_commit:p.error('--source-commit required')
    if args.publish_built:print(publish(args.publish_built,args.source_commit));return
    if not args.workdir:p.error('--workdir required')
    print(build(args.workdir,args.source_commit))
if __name__=='__main__':main()
