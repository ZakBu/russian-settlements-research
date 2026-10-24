#!/usr/bin/env python3
"""Rebuild zero-level systems from frozen source releases, or reuse road evidence.

Full mode never calls live pickup APIs. Compact mode checks a delivered bundle
and recomputes screens, all declared L0 scenarios, higher stages and the atlas.
The accepted census, previous releases and published result versions are read-only.
"""
from __future__ import annotations
import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

REPO=Path(__file__).resolve().parents[2]
SCRIPT=REPO/'scripts/sgrt_zero'
TAG='sgrt-zero-systems-20261025-v1'
PREFIX='sgrt/zero20261025'
SOURCE_TAG='sgrt-zero-inputs-20261025-v1'
SOURCE_MANIFEST_SHA256='d9c8617dadbed91d92cf0cf1e139af67fddf5e9c33c7c50f09cd577c0c664ddc'
MEDICAL_TAG='sgrt-zero-medical-inputs-20261025-v1'
MEDICAL_PDF='TERREESTRMO2021_31.12.2021.pdf'
MEDICAL_SHA256='f8fca17deb75e86b711b3c18a15d909e7341b9baa53b3d93ae6f383835de5c6c'
MEDICAL_BYTES=2151654
MEDICAL_MANIFEST_SHA256='8c7a08e101a9dc36874c9fd9c4932e5184bebf882efd5d141932222436aa0c60'
MEDICAL_BASE='https://github.com/ZakBu/russian-settlements-research/releases/download/'+MEDICAL_TAG+'/'
FEDERAL_TAG='sgrt-zero-federal-medical-inputs-20261025-v1'
FEDERAL_ARCHIVE='SpravNSI_20261023.zip'
FEDERAL_SHA256='e7bab4fa92ba0273faf18d6bfb97c368c3fd0b66290c3b2a82d82bc47ff6db42'
FEDERAL_BYTES=93455460
FEDERAL_MANIFEST_SHA256='8062fa9a3c48acf4f8c39df8914afb37eaf22acef0ee60a7cf0208f750ef7397'
FEDERAL_BASE='https://github.com/ZakBu/russian-settlements-research/releases/download/'+FEDERAL_TAG+'/'
SOURCE_BASE='https://github.com/ZakBu/russian-settlements-research/releases/download/'+SOURCE_TAG+'/'
MASS='sgrt/mass20261024'
PILOT='sgrt/pilot20261024'
HIST='research/sgrt_word_completion_20261021'
TRANSPORT=PILOT+'/outputs/transport'
ROAD_COORDS=HIST+'/transport/cycle06_network2021_access_v2/road_nodes'
SCENARIOS=['daily_20_school30_wb','daily_10_school15_wb','daily_30_school30_wb','core3_20_school30','daily_20_school30_yandex']
CORE_FAMILIES=['medical_basic','school','grocery']
MEDICAL_CORRECTED=['medical_basic_primary','medical_physician_primary','medical_day_hospital','medical_inpatient','medical_hightech_licensed',
                   'medical_specialized','unspecified_healthcare','mapped_hospital_service_unknown_level']
MASS_FILES={
 'reference':MASS+'/context/census_reference.parquet',
 'agriculture':MASS+'/context/settlement_agriculture_context.parquet',
 'workforce':MASS+'/context/settlement_partial_workforce.parquet',
 'licensed_supply':MASS+'/medical-corrected/supply.parquet',
 'licensed_sites':MASS+'/medical-corrected/sites_matched.parquet',
 'preschool':MASS+'/education/official_preschool_supply.parquet',
 'endpoints':MASS+'/routes/endpoints.parquet',
}
PILOT_FILES={
 'health_history':PILOT+'/inputs/'+HIST+'/medical/history_20210101/osm_medical_inventory.parquet',
 'education_history':PILOT+'/inputs/'+HIST+'/education/education_objects_2021.parquet',
 'legacy':TRANSPORT+'/legacy_nodes_minimal.parquet',
 'road_origins':TRANSPORT+'/route_origin_index.parquet',
}
HIST_FILES={
 'health_current':HIST+'/medical/current_20261019/osm_medical_inventory.parquet',
 'education_current':HIST+'/education/education_objects.parquet',
 'commerce':HIST+'/model_inputs_cycle07/institutional_relink477_v1/commerce/source_objects_relinked.parquet',
}


def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for block in iter(lambda:stream.read(4<<20),b''):h.update(block)
 return h.hexdigest()


def run(script,*arguments):
 command=[sys.executable,str(script),*map(str,arguments)]
 print('RUN',' '.join(command),flush=True)
 env=os.environ.copy();env['OMP_NUM_THREADS']='1';env['OPENBLAS_NUM_THREADS']='1'
 subprocess.run(command,cwd=REPO,env=env,check=True)


def catalog_plan(path,patterns,profile):
 c=json.loads(Path(path).read_text());rows=[r for r in c['files'] if profile in r['profiles'] and any(fnmatch.fnmatchcase(r['path'],p) for p in patterns)]
 missing=[p for p in patterns if not any(fnmatch.fnmatchcase(r['path'],p) for r in rows)]
 if missing:raise ValueError('Required catalogue input absent: '+repr(missing))
 assets={c['objects'][r['blob']]['asset'] for r in rows}
 return {'files':len(rows),'logical_bytes':sum(r['bytes'] for r in rows),
  'archive_download_bytes':sum(a['bytes'] for a in c['assets'] if a['asset'] in assets),
  'patterns':patterns,'profile':profile}


def plan():
 return {'mode':'full_frozen_sources_and_new_directed_roads','source_release_tag':SOURCE_TAG,
  'source_manifest_sha256_default':SOURCE_MANIFEST_SHA256,'unconfigured_pin_requires_explicit_CLI_sha256':SOURCE_MANIFEST_SHA256 is None,
  'live_pickup_APIs_used':False,'census_modified':False,
  'federal_medical_source':{'tag':FEDERAL_TAG,'archive':FEDERAL_ARCHIVE,'sha256':FEDERAL_SHA256,'manifest_sha256':FEDERAL_MANIFEST_SHA256,'snapshot':'2026-10-23'},
  'supplemental_medical_source':{'tag':MEDICAL_TAG,'asset':MEDICAL_PDF,'sha256':MEDICAL_SHA256,'manifest_sha256':MEDICAL_MANIFEST_SHA256,'bytes':MEDICAL_BYTES,'year':2021,'current_2026_operation_verified':False},
  'catalogues':{
   'population':catalog_plan(REPO/'data/catalog.json',['data/population/settlements_census_wide.parquet'],'core'),
   'mass':catalog_plan(REPO/'data/mass_catalog_20261024.json',list(MASS_FILES.values()),'core'),
   'pilot':catalog_plan(REPO/'data/pilot_catalog_20261024.json',list(PILOT_FILES.values())+[TRANSPORT+'/graph/graph_npz_parts/*.bin'],'core'),
   'historical':catalog_plan(REPO/'data/catalog.json',list(HIST_FILES.values())+[ROAD_COORDS+'/*.parquet'],'all')},
  'declared_l0_scenarios':SCENARIOS,'higher_new_function_sets_attempted':4,'extended_scenario_stages':6,
  'compact_scope':'Recompute screens/L0/higher/logic/atlas from verified source and road tables, without a new route search',
  'source_epochs_are_separate':True,'Moscow_only_top_forced':False,
  'graph_road_coordinates_and_global_external_reference_not_duplicated_in_result_archive':True}


def download(url,path,expected_sha256=None,expected_bytes=None):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():
  if expected_sha256 and digest(path)!=expected_sha256:raise ValueError('Existing pinned input differs: '+str(path))
  if expected_bytes is not None and path.stat().st_size!=expected_bytes:raise ValueError('Input size differs: '+str(path))
  return path
 partial=path.with_suffix(path.suffix+'.partial')
 request=urllib.request.Request(url,headers={'User-Agent':'SGRT-Zero-Reproduction/1'})
 try:
  with urllib.request.urlopen(request,timeout=180) as response,partial.open('wb') as output:shutil.copyfileobj(response,output,4<<20)
  if expected_sha256 and digest(partial)!=expected_sha256:raise ValueError('Downloaded input SHA differs: '+url)
  if expected_bytes is not None and partial.stat().st_size!=expected_bytes:raise ValueError('Downloaded input size differs: '+url)
  partial.replace(path)
 except BaseException:
  partial.unlink(missing_ok=True);raise
 return path


def safe_extract(archive,output):
 output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(archive) as z:
  for member in z.infolist():
   target=(output/member.filename).resolve()
   if not target.is_relative_to(output):raise ValueError('Unsafe ZIP member: '+member.filename)
   if (member.external_attr>>16)&0o170000==0o120000:raise ValueError('Symlink in source ZIP')
  z.extractall(output)


def fetch_frozen_sources(work,pin):
 if not pin or not re.fullmatch('[0-9a-fA-F]{64}',pin):raise ValueError('Full mode requires the immutable source manifest SHA256')
 dest=work/'source';manifest_path=download(SOURCE_BASE+'source_manifest.json',dest/'source_manifest.json',pin)
 manifest=json.loads(manifest_path.read_text())
 if manifest.get('source_release_tag')!=SOURCE_TAG:raise ValueError('Unexpected frozen source tag')
 archive=manifest['archive']
 if archive['name']!='source-inputs.zip':raise ValueError('Unexpected source archive')
 zipped=download(SOURCE_BASE+archive['name'],dest/archive['name'],archive['sha256'],archive['bytes'])
 safe_extract(zipped,dest)
 source=dest/'source_inputs'
 for relative,meta in manifest['files'].items():
  path=(source/relative).resolve()
  if not path.is_relative_to(source.resolve()):raise ValueError('Unsafe source manifest path')
  if not path.is_file() or path.stat().st_size!=meta['bytes'] or digest(path)!=meta['sha256']:raise ValueError('Frozen source differs: '+relative)
 internal=json.loads((source/'source_manifest.json').read_text())
 if internal['files']!=manifest['files'] or internal['snapshot_label']!=manifest['snapshot_label']:raise ValueError('External/internal source manifest mismatch')
 snapshot=manifest['snapshot_label']
 if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',snapshot):raise ValueError('Invalid snapshot label')
 return source,manifest


def fetch_medical_source(inputs):
 dest=inputs/'frozen_medical_sources'
 path=download(MEDICAL_BASE+'medical_source_manifest.json',dest/'medical_source_manifest.json',MEDICAL_MANIFEST_SHA256)
 manifest=json.loads(path.read_text())
 if manifest.get('release_tag')!=MEDICAL_TAG or manifest.get('source_reference_year')!=2021:raise ValueError('Unexpected supplemental medical source')
 matches=[a for a in manifest.get('assets',[]) if a.get('asset')==MEDICAL_PDF]
 if len(matches)!=1 or matches[0].get('sha256')!=MEDICAL_SHA256 or matches[0].get('bytes')!=MEDICAL_BYTES:raise ValueError('Medical PDF declaration differs from pinned source')
 return download(MEDICAL_BASE+MEDICAL_PDF,dest/MEDICAL_PDF,MEDICAL_SHA256,MEDICAL_BYTES)


def fetch_federal_source(inputs):
 dest=inputs/'frozen_federal_medical'
 path=download(FEDERAL_BASE+'federal_medical_source_manifest.json',dest/'federal_medical_source_manifest.json',FEDERAL_MANIFEST_SHA256)
 manifest=json.loads(path.read_text())
 if manifest.get('release_tag')!=FEDERAL_TAG or manifest.get('snapshot_label')!='2026-10-23':raise ValueError('Unexpected federal medical reference date')
 matches=[a for a in manifest.get('assets',[]) if a.get('asset')==FEDERAL_ARCHIVE]
 if len(matches)!=1 or matches[0].get('sha256')!=FEDERAL_SHA256 or matches[0].get('bytes')!=FEDERAL_BYTES:raise ValueError('Federal source archive differs from pinned declaration')
 return download(FEDERAL_BASE+FEDERAL_ARCHIVE,dest/FEDERAL_ARCHIVE,FEDERAL_SHA256,FEDERAL_BYTES)


def fetch_catalog(path,patterns,work,profile):
 args=['fetch','--catalog',path,'--profile',profile,'--dest',work/'dependencies','--cache',work/'cache','--keep-archives']
 for pattern in patterns:args+=['--match',pattern]
 run(REPO/'scripts/research_data.py',*args)


def copy_file(source,target):
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)


def full_prepare(work,pin):
 source,manifest=fetch_frozen_sources(work,pin)
 fetch_catalog(REPO/'data/catalog.json',['data/population/settlements_census_wide.parquet'],work,'core')
 fetch_catalog(REPO/'data/mass_catalog_20261024.json',list(MASS_FILES.values()),work,'core')
 fetch_catalog(REPO/'data/pilot_catalog_20261024.json',list(PILOT_FILES.values())+[TRANSPORT+'/graph/graph_npz_parts/*.bin'],work,'core')
 fetch_catalog(REPO/'data/catalog.json',list(HIST_FILES.values())+[ROAD_COORDS+'/*.parquet'],work,'all')
 deps=work/'dependencies';inputs=work/'inputs';inputs.mkdir(exist_ok=True)
 paths={key:deps/value for mapping in [MASS_FILES,PILOT_FILES,HIST_FILES] for key,value in mapping.items()}
 paths['population']=deps/'data/population/settlements_census_wide.parquet'
 for key,path in paths.items():copy_file(path,inputs/(key+'.parquet'))
 copy_file(paths['agriculture'],work/'context/settlement_agriculture_context.parquet')
 copy_file(paths['workforce'],work/'context/settlement_partial_workforce.parquet')
 snapshot=manifest['snapshot_label'];date=snapshot.replace('-','')
 run(SCRIPT/'city_context.py','--reference',paths['reference'],'--population-wide',paths['population'],
     '--input',source/'city_context','--output',work/'context')
 ref=work/'context/analysis_reference.parquet'
 run(SCRIPT/'health.py','--osm-current',paths['health_current'],'--osm-history',paths['health_history'],
     '--official-supply',paths['licensed_supply'],'--reference',ref,'--legacy',paths['legacy'],'--output',work/'health')
 run(SCRIPT/'health.py','correct-public-scope','--health-root',work/'health',
     '--official-supply',paths['licensed_supply'],'--official-sites',paths['licensed_sites'],'--reference',ref,
     '--output',work/'health/strict_control')
 run(SCRIPT/'medical_scope.py','--base-health',work/'health/strict_control','--legacy-sites',paths['licensed_sites'],
     '--legacy-supply',paths['licensed_supply'],'--reference',ref,'--output',work/'health/legacy_primary_child_scope_corrected')
 medical_pdf=fetch_medical_source(inputs)
 run(SCRIPT/'saratov_registry.py','--pdf',medical_pdf,'--reference',ref,
     '--output',work/'health/saratov_2021_supplement','--base-health',work/'health/legacy_primary_child_scope_corrected',
     '--combined-output',work/'health/saratov_control')
 federal_archive=fetch_federal_source(inputs)
 run(SCRIPT/'medical_regional_sources.py','--archive',federal_archive,'--input-dir',work/'source/federal_xml',
     '--output',work/'federal_medical/normalized','--asof','2026-10-23')
 run(SCRIPT/'federal_medical_addresses.py','--source',work/'federal_medical/normalized/F038_current.parquet',
     '--reference',ref,'--output',work/'federal_medical/addresses')
 run(SCRIPT/'federal_medical_functions.py','--input',work/'federal_medical/normalized/care_site_profiles_current.parquet',
     '--codebooks',work/'source/federal_xml','--asof','2026-10-23','--output',work/'federal_medical/functions')
 run(SCRIPT/'federal_medical_integrate.py','--classified',work/'federal_medical/functions/care_rows_classified.parquet',
     '--evidence',work/'federal_medical/functions/service_evidence_by_care_address.parquet',
     '--addresses',work/'federal_medical/addresses/F038_current_np_identity.parquet','--reference',ref,
     '--base-health',work/'health/legacy_primary_child_scope_corrected','--historical-supplement',work/'health/saratov_2021_supplement',
     '--output',work/'health/public_scope_corrected')
 # These seven generated XML files are reproducible from the pinned ZIP.
 # Removing only these exact scratch names avoids retaining another 1.9GB.
 for code in ['F032','F033','F034','F038','V002','V006','V008']:
  (work/'source/federal_xml'/(code+'.xml')).unlink(missing_ok=True)
 run(SCRIPT/'education.py','--current',paths['education_current'],'--historical',paths['education_history'],
     '--official',paths['preschool'],'--reference',ref,'--legacy',paths['legacy'],
     '--city-context',work/'context/city_context_origins.parquet','--output',work/'education')
 run(SCRIPT/'commerce.py','--osm',paths['commerce'],'--wb',source/'wildberries.json.gz',
     '--reference',ref,'--legacy',paths['legacy'],'--population',paths['population'],
     '--wb-snapshot',snapshot,'--output',work/'commerce')
 for operator,prefix,folder in [('yandex','yandex','yandex'),('fivepost','fivepost','fivepost')]:
  run(SCRIPT/'commerce.py',operator,'--source',source/(prefix+'_public_widget_pickup_'+date+'.json.gz'),
      '--reference',ref,'--population',paths['population'],'--snapshot',snapshot,'--output',work/'commerce'/folder)
 # Raw source corpus stays portable. The global eFUA ZIP is shared with the
 # input release; only the extracted analysis geometry enters the result.
 copy_file(work/'source/source_manifest.json',inputs/'source_manifest.json')
 for path in source.rglob('*'):
  if path.is_file() and path.name!='ghs_fua_2015.zip':copy_file(path,inputs/'frozen_public_sources'/path.relative_to(source))
 fua_dir=work/'source/external_fua';safe_extract(source/'ghs_fua_2015.zip',fua_dir)
 gpkg=list(fua_dir.rglob('*.gpkg'))
 if len(gpkg)!=1:raise ValueError('Expected one pinned global eFUA GeoPackage')
 run(SCRIPT/'logic_checks.py','extract-external-fua','--gpkg',gpkg[0],'--reference',ref,
     '--output',work/'literature/external_fua_russia')
 road_args=['--road-nodes',deps/ROAD_COORDS,'--road-origins',paths['road_origins'],'--graph-dir',deps/TRANSPORT/'graph']
 run(SCRIPT/'transport.py','--sites',work/'health/public_scope_corrected/physical_sites.parquet',
     work/'education/physical_sites.parquet',work/'commerce/sites.parquet',
     work/'commerce/fivepost/sites_5post_current.parquet',work/'commerce/fivepost/sites_grocery_current_host_proxy.parquet',
     '--np-supply',work/'health/public_scope_corrected/np_supply.parquet',work/'education/np_supply.parquet',
     work/'commerce/supply.parquet',work/'commerce/fivepost/supply_5post_current.parquet',
     work/'commerce/fivepost/supply_grocery_current_host_proxy.parquet',
     '--endpoints',paths['endpoints'],'--additional-origins',work/'context/city_context_origins.parquet',
     *road_args,'--output',work/'routes')
 for folder,site,supply in [('routes_wb',work/'commerce/sites_wb_current.parquet',work/'commerce/supply_wb_current.parquet'),
                            ('routes_yandex',work/'commerce/yandex/sites_yandex_current.parquet',work/'commerce/yandex/supply_yandex_current.parquet')]:
  run(SCRIPT/'transport.py','--sites',site,'--np-supply',supply,'--endpoints',work/'routes/endpoints.parquet',
      *(['--geometry-cache',work/'routes/provider_road_seeds.parquet'] if folder=='routes_wb' else
        ['--road-nodes',deps/ROAD_COORDS,'--road-origins',paths['road_origins']]),
      '--graph-dir',deps/TRANSPORT/'graph','--output',work/folder)
 run(SCRIPT/'combine_nearest.py','--component','osm_grocery_2021='+str(work/'routes/nearest/daily_grocery.parquet'),
     '--component','current_food_host_2026='+str(work/'routes/nearest/daily_grocery_current_retail_host.parquet'),
     '--output',work/'derived_nearest/daily_grocery_evidence_union.parquet')
 (work/'analysis_options.json').write_text(json.dumps({'grocery_nearest':'derived_nearest/daily_grocery_evidence_union.parquet',
  'grocery_union_is_one_function':True,'positive_current_host_evidence_is_not_complete_shop_inventory':True},indent=2)+'\n')
 (work/'full_prepare.json').write_text(json.dumps({'mode':'full_frozen_inputs_and_new_directed_routes',
  'snapshot_label':snapshot,'source_release_tag':SOURCE_TAG,'source_manifest_sha256':pin,
  'supplemental_medical_source':{'tag':MEDICAL_TAG,'sha256':MEDICAL_SHA256,'source_year':2021,'historical_proxy_not_current_operation':True},
  'federal_medical_source':{'tag':FEDERAL_TAG,'sha256':FEDERAL_SHA256,'reference_date':'2026-10-23','coarse_NP_offers_not_geocoded_buildings':True},
  'census_population_sha256':digest(paths['population']),'census_modified':False,
  'previous_licensed_and_rosstat_normalized_tables_reused':True,'live_API_calls':False,
  'new_directed_routing':True,'derived_inputs':{key:digest(path) for key,path in paths.items()}},ensure_ascii=False,indent=2)+'\n')


def verify_bundle(bundle):
 root=Path(bundle).resolve();manifest=json.loads((root/'checksums.json').read_text())
 for relative,expected in manifest.items():
  p=(root/relative).resolve()
  if not p.is_relative_to(root):raise ValueError('Unsafe bundle manifest path')
  if not p.is_file() or digest(p)!=expected:raise ValueError('Bundle file differs: '+relative)
 return len(manifest)


def compact_prepare(bundle,work):
 bundle=Path(bundle).resolve();count=verify_bundle(bundle)
 for name in ['analysis_options.json']:
  if (bundle/name).exists():copy_file(bundle/name,work/name)
 for folder in ['inputs','context','health/public_scope_corrected','health/saratov_2021_supplement','health/legacy_primary_child_scope_corrected','education','commerce','derived_nearest','routes','routes_wb','routes_yandex','literature/external_fua_russia','federal_medical']:
  source=bundle/folder
  if source.exists():shutil.copytree(source,work/folder,dirs_exist_ok=True)
 (work/'compact_prepare.json').write_text(json.dumps({'mode':'compact_reuse_verified_sources_and_raw_nearest',
  'source_bundle_files_verified':count,'new_directed_routing':False,'new_live_API_calls':False,
  'recomputed':['daily_admission','five_L0_scenarios','four_higher_new_function_sets','six_extended_stage_comparisons','actual_invariant_audits','arithmetic_checks','atlas']},indent=2)+'\n')


def route_view(work):
 """Final logical view: replace corrected medical classes, preserve originals."""
 base={p.stem:p for p in (work/'routes/nearest').glob('*.parquet')}
 for folder in ['routes_health_corrected','routes_5post','routes_saratov_scope_corrected','routes_pediatric_scope_corrected','routes_complete_scope_corrected']:
  for path in (work/folder/'nearest').glob('*.parquet'):base[path.stem]=path
 if not base:raise ValueError('No final raw nearest evidence')
 return base


def materialize_route_view(work):
 target=work/'routes_final/nearest';target.mkdir(parents=True,exist_ok=True)
 sources=route_view(work);expected={code+'.parquet' for code in sources}
 stale={p.name for p in target.glob('*.parquet')}-expected
 for name in stale:(target/name).unlink()
 for code,path in sources.items():copy_file(path,target/(code+'.parquet'))
 metadata={code:{'source_path':str(path),'sha256':digest(path)} for code,path in sorted(sources.items())}
 (work/'routes_final/view.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
 return target


def grocery_override(work):
 options=work/'analysis_options.json'
 if not options.exists():return None
 relative=json.loads(options.read_text()).get('grocery_nearest')
 if not relative:return None
 path=(work/relative).resolve()
 if not path.is_relative_to(work.resolve()) or not path.is_file():raise ValueError('Declared grocery override missing or outside portable work directory')
 return path


def expected_stage_directories(work):
 main=SCENARIOS[0];strict=work/'upward'/main;extended=work/'upward_extended'/main
 first=sorted(strict.glob('[0-9][0-9]_*'))
 later=sorted(extended.glob('*/[0-9][0-9]_*'))
 if len(first)!=4 or {p.name[:2] for p in first}!={'01','02','03','04'}:
  raise ValueError('Incomplete strict hierarchy: four actual stages required')
 pairs={(p.parent.name,p.name[:2]) for p in later}
 expected={(mode,stage) for mode in ['all_declared','partial_positive_two_domains'] for stage in ['02','03','04']}
 if len(later)!=6 or pairs!=expected:raise ValueError('Incomplete extended hierarchy: all six actual stages required')
 return first,later


def validate_actual_audits(work):
 for relative,count in [('checks/level_zero_actual.json',1),('checks/upward_actual.json',4),('checks/extended_actual.json',6)]:
  path=work/relative
  if not path.is_file():raise ValueError('Actual scientific audit missing: '+relative)
  value=json.loads(path.read_text());reports=[value] if isinstance(value,dict) else value
  if not isinstance(reports,list) or len(reports)!=count:raise ValueError('Incomplete actual audit: '+relative)
  for report in reports:
   failures=report.get('failures')
   if not isinstance(failures,dict) or not failures:raise ValueError('Missing actual failure counts: '+relative)
   bad={key:n for key,n in failures.items() if n!=0}
   if bad:raise ValueError('Actual scientific audit failed: '+relative+' '+repr(bad))


def canonical_health_supply(work):
 for role in ['health/public_scope_complete_corrected','health/public_scope_pediatric_corrected','health/public_scope_child_corrected','health/public_scope_corrected']:
  path=work/role/'np_supply.parquet'
  if path.is_file():return path
 raise ValueError('Canonical healthcare supply missing')


def validate_primary_scope_report(path):
 failures=json.loads(Path(path).read_text()).get('failures')
 if not isinstance(failures,dict) or not failures:raise ValueError('Missing actual primary-care scope failure counts')
 bad={key:value for key,value in failures.items() if value!=0}
 if bad:raise ValueError('Actual primary-care source scope audit failed: '+repr(bad))


def check_medical_primary_scope(work):
 functions=next((work/role for role in ['federal_medical/functions_complete_scope_corrected',
  'federal_medical/functions_unit_scope_corrected','federal_medical/functions']
  if (work/role/'care_rows_classified.parquet').is_file()),None)
 if functions is None:return
 legacy=work/'health/legacy_final_unit_scope_corrected'
 if not legacy.is_dir():legacy=work/'health/legacy_primary_child_scope_corrected'
 health=canonical_health_supply(work).parent;output=work/'checks/medical_primary_scope_actual.json'
 run(SCRIPT/'logic_checks.py','check-medical-primary-scope',
     '--legacy-evidence',legacy/'legacy_source_evidence_with_scope.parquet',
     '--federal-care',functions/'care_rows_classified.parquet','--np-supply',health/'np_supply.parquet',
     '--physical-sites',health/'physical_sites.parquet','--output',output)
 validate_primary_scope_report(output)


def analyses(work):
 override=grocery_override(work)
 reference=work/'context/analysis_reference.parquet';nearest=materialize_route_view(work)
 wb=work/'routes_wb/nearest/parcel_pickup_wildberries_current.parquet'
 yandex=work/'routes_yandex/nearest/parcel_pickup_yandex_current.parquet'
 run(SCRIPT/'screens.py','--routes',nearest,'--reference',reference,'--wb-nearest',wb,'--yandex-nearest',yandex,
     *(['--grocery-nearest',override] if override else []),'--scenarios',*SCENARIOS,'--output',work/'screens_final')
 for scenario in SCENARIOS:
  families=CORE_FAMILIES if scenario=='core3_20_school30' else [*CORE_FAMILIES,'parcel_pickup']
  run(SCRIPT/'hierarchy.py','--edges',work/'screens_final/daily_edges.parquet','--reference',reference,
      '--families',*families,'--core-families',*CORE_FAMILIES,'--scenario-id',scenario,'--output',work/'hierarchy'/scenario)
 # Upward reads the declared final source files. No staged handoff or old
 # rejected medical routes are allowed to shadow the corrected logical view.
 logical=work/'analysis_routes';link=logical/'routes/nearest';link.parent.mkdir(parents=True,exist_ok=True)
 if link.exists() and (not link.is_symlink() or link.resolve()!=nearest.resolve()):raise ValueError('Stale copied route view; choose a clean work directory')
 if not link.exists():link.symlink_to(nearest.resolve(),target_is_directory=True)
 main=SCENARIOS[0]
 run(SCRIPT/'upward.py','--root',logical,'--l0-directory',work/'hierarchy'/main,'--reference',reference,
     '--fua-directory',work/'literature/external_fua_russia','--physician-route',nearest/'medical_physician_primary.parquet',
     '--medical-routes',nearest,'--output',work/'upward'/main)
 run(SCRIPT/'extended.py','--root',logical,'--strict-directory',work/'upward'/main,'--reference',reference,'--output',work/'upward_extended'/main)
 expected_stage_directories(work)
 links=work/'literature/external_fua_russia/settlement_external_fua_links.parquet'
 run(SCRIPT/'logic_checks.py','check-level-zero','--directory',work/'hierarchy'/main,'--reference',reference,'--output',work/'checks/level_zero_actual.json')
 run(SCRIPT/'logic_checks.py','check-upward','--directory',work/'upward'/main,'--level-zero',work/'hierarchy'/main,'--origin-links',links,'--output',work/'checks/upward_actual.json')
 run(SCRIPT/'logic_checks.py','check-extended','--directory',work/'upward_extended'/main,'--strict-directory',work/'upward'/main,'--reference',reference,'--origin-links',links,'--output',work/'checks/extended_actual.json')
 validate_actual_audits(work)
 check_medical_primary_scope(work)
 run(SCRIPT/'logic_checks.py','check-route-arithmetic','--nearest',nearest,'--output',work/'checks/route_arithmetic.json')
 for folder in ['routes_wb','routes_yandex']:
  run(SCRIPT/'logic_checks.py','check-route-arithmetic','--nearest',work/folder/'nearest','--output',work/'checks'/(folder+'_arithmetic.json'))
 scientific_checks(work)
 run(SCRIPT/'population_context.py','--reference',reference,'--analysis-root',work,'--output',work/'population_context_readout')
 run(SCRIPT/'hierarchy_readout.py','--root',work,'--reference',reference,'--output',work/'hierarchy_readout')
 medical_evidence=canonical_health_supply(work).parent/'federal_service_evidence_with_identity.parquet'
 if medical_evidence.is_file():
  run(SCRIPT/'system_complexity.py','--memberships',work/'hierarchy'/main/'level0_memberships.parquet',
      '--medical-evidence',medical_evidence,'--education-sites',work/'education/physical_sites.parquet',
      '--wildberries-sites',work/'commerce/sites_wb_current.parquet','--reference',reference,
      '--external-fua',work/'literature/external_fua_russia/analysis_frame_efua_2015.parquet',
      '--output',work/'functional_complexity')
 run(SCRIPT/'atlas.py','--root',work,'--hierarchy',work/'hierarchy'/main,'--scenario',main,
     '--higher',work/'upward'/main,'--comparison-upward',work/'upward_extended'/main,
     '--health-supply',canonical_health_supply(work),'--output',work/'figures')


def scientific_checks(work):
 import pandas as pd
 ref=pd.read_parquet(work/'context/analysis_reference.parquet')
 expected=set(ref.loc[ref.analysis_origin.fillna(False),'source_record_id'].dropna())
 if len(expected)!=153803:raise ValueError('Full national ordinary+context origin frame missing')
 context=ref[ref.source_record_id.isin(expected)&~ref.ordinary_spatial_2021.fillna(False)]
 if len(context)!=3 or context.budget_population_credit.fillna(True).any():raise ValueError('Nonadditive city contexts changed the population budget')
 records=[]
 for scenario in SCENARIOS:
  folder=work/'hierarchy'/scenario
  members=pd.read_parquet(folder/'level0_memberships.parquet')
  units=pd.read_parquet(folder/'level0_units.parquet')
  if members.origin_id.duplicated().any() or set(members.origin_id)!=expected:raise ValueError('L0 lost or duplicated origins: '+scenario)
  if not units.unit_id.is_unique or units.type_code.isna().any():raise ValueError('L0 units lack unique typed identity')
  if not members.unit_id.isin(units.unit_id).all():raise ValueError('Unknown L0 unit membership')
  records.append({'scenario':scenario,'units':len(units),'members':len(members),'every_unit_typed':True})
 main=SCENARIOS[0];previous=pd.read_parquet(work/'hierarchy'/main/'level0_memberships.parquet')
 for folder in sorted((work/'upward'/main).glob('[0-9][0-9]_*')):
  cross=pd.read_parquet(folder/'subsystem_crosswalk.parquet')
  current=pd.read_parquet(folder/'memberships.parquet')
  if cross.child_unit_id.duplicated().any():raise ValueError('A child is split during promotion')
  predicted=previous[['origin_id','unit_id']].rename(columns={'unit_id':'child_unit_id'}).merge(cross[['child_unit_id','unit_id']],on='child_unit_id',validate='many_to_one')
  if current.origin_id.duplicated().any() or set(current.origin_id)!=expected:raise ValueError('Higher stage lost or duplicated origins')
  a=predicted.set_index('origin_id').unit_id.sort_index();b=current.set_index('origin_id').unit_id.sort_index()
  if list(a.index)!=list(b.index) or not (a.to_numpy()==b.to_numpy()).all():raise ValueError('Higher stage is not the exact union of complete children')
  previous=current
 reports=[]
 for path in sorted((work/'checks').glob('*arithmetic.json')):
  rows=json.loads(path.read_text())
  if not rows:raise ValueError('Empty transport arithmetic check')
  for row in rows:
   if row['origins']!=len(expected) or any(row[k] for k in ['duplicate_origins','negative_cost','no_provider_but_cost','observed_flow_claims','established_attachment_claims']):raise ValueError('Transport check failed: '+str(path))
   if row['without_time_cutoff']!=len(expected):raise ValueError('Raw long-distance outcomes were clipped')
   if row['max_decomposition_error_minutes'] is not None and row['max_decomposition_error_minutes']>1e-8:raise ValueError('Transport arithmetic residual')
  reports.extend(rows)
 if not reports:raise ValueError('No transport arithmetic evidence')
 declared=set(route_view(work))
 for folder in ['routes_wb','routes_yandex']:
  declared.update(p.stem for p in (work/folder/'nearest').glob('*.parquet'))
 if {row['service'] for row in reports}!=declared:raise ValueError('Not every declared nearest service was numerically checked')
 output={'analysis_origins':len(expected),'ordinary_origins':153800,'nonadditive_context_origins':3,
   'l0_scenarios':records,'higher_origins_retained':len(previous),'transport_tables_checked':len(reports),
   'observed_trips_established':False,'all_unknown_does_not_mean_no_dependency':True}
 (work/'checks/scientific_checks.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
 return output


def files_under(base,relative,*,skip_names=()):
 folder=base/relative
 if not folder.exists():return {}
 out={}
 for p in folder.rglob('*'):
  if not p.is_file() or p.is_symlink():continue
  path=p.relative_to(folder)
  if any(x in {'__pycache__','dependencies','cache','download-cache','raw','archive','checks','source-history.git'} for x in path.parts[:-1]):continue
  if p.name in skip_names or p.suffix in {'.log','.partial','.rar'}:continue
  if p.suffix=='.csv' and (p.stat().st_size>1_000_000 or p.with_suffix('.parquet').exists()):continue
  out[(Path(relative)/path).as_posix()]=p
 return out


def source_corpus(work):
 """Preserve exact locally used source tables from recorded input provenance."""
 out={}
 for name,key in [('health/summary.json','inputs_sha256'),('education/summary.json','source_input_sha256')]:
  summary=work/name
  if not summary.exists():continue
  for filename,sha in json.loads(summary.read_text()).get(key,{}).items():
   path=Path(filename)
   frozen=work/('inputs/source_corpus/'+sha[:16]+'_'+path.name)
   if frozen.is_file():path=frozen
   if not path.is_file() or digest(path)!=sha:raise ValueError('Recorded source corpus missing or differs: '+filename)
   out['inputs/source_corpus/'+sha[:16]+'_'+path.name]=path
 for summary in [work/'commerce/summary.json',work/'commerce/yandex/summary.json',work/'commerce/fivepost/summary.json']:
  if not summary.exists():continue
  for row in json.loads(summary.read_text()).get('source_files',[]):
   path=Path(row['path']);sha=row['sha256']
   frozen=work/('inputs/source_corpus/'+sha[:16]+'_'+path.name)
   if frozen.is_file():path=frozen
   if not path.is_file() or digest(path)!=sha:raise ValueError('Recorded commerce source differs: '+str(path))
   out['inputs/source_corpus/'+sha[:16]+'_'+path.name]=path
 # Every retained route class has exact input provenance. Preserve even a
 # superseded NP table if an unchanged-class control still refers to it;
 # identical normalized tables are deduplicated by the object-store packager.
 for prep in work.glob('routes*/provider_preparation.json'):
  for filename,sha in json.loads(prep.read_text()).get('source_input_sha256',{}).items():
   path=Path(filename)
   if path.name=='provider_road_seeds.parquet':continue
   frozen=work/('inputs/source_corpus/'+sha[:16]+'_'+path.name)
   if frozen.is_file():path=frozen
   if not path.is_file() or digest(path)!=sha:raise ValueError('Recorded route input differs: '+filename)
   out['inputs/source_corpus/'+sha[:16]+'_'+path.name]=path
 return out


def payload_files(work):
 work=Path(work);out=source_corpus(work)
 for folder in ['inputs','context','health/public_scope_corrected','health/saratov_2021_supplement','health/legacy_primary_child_scope_corrected','education','commerce','derived_nearest','literature/external_fua_russia','routes_wb','routes_yandex','population_context_readout','hierarchy_readout','functional_complexity','figures','checks']:
  out.update(files_under(work,folder))
 # Only accepted public-scope health and current source tables. Original
 # intermediate health classifications are reconstructed in full mode.
 out={k:v for k,v in out.items() if not any(s in k for s in ['/dependencies/','/federal_context/','/operator_service_sites.','/operator_specific_supply.'])}
 # Prepared national pass predates the canonical in-build city binding.
 # Its frozen V2 tables supersede only equal logical commerce roles.
 for role in ['normalized','functions','addresses']:
  folder=work/'federal_medical'/role
  for pattern in ['*.parquet','*.json']:
   for path in folder.glob(pattern):out[path.relative_to(work).as_posix()]=path
 final_functions=work/'federal_medical/functions_unit_scope_corrected'
 if (work/'federal_medical/functions_complete_scope_corrected').exists():final_functions=work/'federal_medical/functions_complete_scope_corrected'
 for pattern in ['*.parquet','*.json']:
  for path in final_functions.glob(pattern):out['federal_medical/functions/'+path.name]=path
 for source_role,target_role in [('health/public_scope_child_corrected','health/public_scope_corrected'),('health/saratov_2021_supplement_child_corrected','health/saratov_2021_supplement'),('health/public_scope_pediatric_corrected','health/public_scope_corrected'),('health/public_scope_complete_corrected','health/public_scope_corrected'),('health/legacy_final_unit_scope_corrected','health/legacy_primary_child_scope_corrected'),('health/saratov_final_unit_scope_supplement','health/saratov_2021_supplement')]:
  for relative,path in files_under(work,source_role).items():
   out[target_role+'/'+str(Path(relative).relative_to(source_role))]=path
 final_commerce=work/'commerce/federal_context'
 if final_commerce.exists():
  for p in final_commerce.glob('*'):
   if p.is_file() and p.suffix in {'.parquet','.json'}:out['commerce/'+p.name]=p
 screens='screens_final' if (work/'screens_final').is_dir() else 'screens_public_scope_corrected'
 for rel,path in files_under(work,screens).items():out['screens_final/'+str(Path(rel).relative_to(screens))]=path
 for scenario in SCENARIOS:out.update(files_under(work,'hierarchy/'+scenario))
 out.update(files_under(work,'upward/'+SCENARIOS[0]))
 out.update(files_under(work,'upward_extended/'+SCENARIOS[0]))
 # Do not duplicate the superseded route files or the 48MB graph snap cache.
 # Preserve a single final class-level table plus the endpoints and optional
 # sampling evidence; raw nearest data are sufficient for compact rebuilding.
 for code,path in route_view(work).items():out['routes/nearest/'+code+'.parquet']=path
 for name in ['endpoints.parquet']:
  if (work/'routes'/name).is_file():out['routes/'+name]=work/'routes'/name
 for p in (work/'routes_final').glob('*.json'):out['routes/'+p.name]=p
 for folder in ['routes','routes_health_corrected','routes_5post','routes_saratov_scope_corrected','routes_pediatric_scope_corrected','routes_complete_scope_corrected']:
  for p in (work/folder).glob('*'):
   if p.is_file() and p.suffix in {'.json','.parquet'} and p.name not in {'provider_road_seeds.parquet','endpoints.parquet'}:
    out['routes/provenance/'+folder+'/'+p.name]=p
 for name in ['full_prepare.json','compact_prepare.json','analysis_options.json','prepared_frozen25_sources.json','raw_routes_frozen_manifest.json']:
  if (work/name).is_file():out[name]=work/name
 return out


def check_complete(work):
 grocery_override(work)
 required=['context/analysis_reference.parquet','context/city_context_origins.parquet',
  'health/public_scope_corrected/np_supply.parquet','health/public_scope_corrected/physical_sites.parquet',
  'education/physical_sites.parquet','education/np_supply.parquet','commerce/sites.parquet','commerce/supply.parquet',
  'commerce/yandex/sites_yandex_current.parquet','commerce/fivepost/sites_5post_current.parquet',
  'routes_wb/nearest/parcel_pickup_wildberries_current.parquet','routes_yandex/nearest/parcel_pickup_yandex_current.parquet',
  'literature/external_fua_russia/analysis_frame_efua_2015.parquet',
  'literature/external_fua_russia/settlement_external_fua_status.parquet',
  'upward/'+SCENARIOS[0]+'/summary.json','upward_extended/'+SCENARIOS[0]+'/summary.json','population_context_readout/summary.json','hierarchy_readout/summary.json','checks/scientific_checks.json','figures/zero_level_atlas.pdf','figures/atlas_manifest.json','figures/01_national_statuses.png']
 if (work/'inputs/frozen_federal_medical/federal_medical_source_manifest.json').exists():
  required += ['federal_medical/normalized/'+code+'_'+kind+'.parquet' for code in ['F032','F033','F034','F038'] for kind in ['current','history']]
  required += ['federal_medical/normalized/'+name for name in ['V002_codebook.json','V006_codebook.json','V008_codebook.json','source_summary.json','join_audit.json','care_site_profiles_current.parquet']]
  required += ['federal_medical/functions/'+name for name in ['care_rows_classified.parquet','service_evidence_by_care_address.parquet','summary.json']]
  required += ['federal_medical/addresses/F038_current_np_identity.parquet','federal_medical/addresses/address_identity_summary.json']
  required += ['health/legacy_primary_child_scope_corrected/'+name for name in ['legacy_sites_all_rows.parquet','legacy_source_evidence_with_scope.parquet','child_primary_confirmations_held.parquet','physical_child_scope_audit.parquet','summary.json']]
  required += ['checks/medical_primary_scope_actual.json']
 for scenario in SCENARIOS:required += ['hierarchy/'+scenario+'/level0_units.parquet','hierarchy/'+scenario+'/level0_memberships.parquet','hierarchy/'+scenario+'/summary.json']
 missing=[x for x in required if not (work/x).is_file()]
 if missing:raise ValueError('Cannot package incomplete zero-level result: '+repr(missing))
 strict,extended=expected_stage_directories(work)
 for folder in strict+extended:
  names=['units.parquet','memberships.parquet','subsystem_crosswalk.parquet','higher_edge_evidence.parquet','summary.json']
  if folder in extended:names += ['parent_decisions.parquet','selected_core_candidates.parquet','parent_candidates.parquet']
  absent=[str(folder/name) for name in names if not (folder/name).is_file()]
  if absent:raise ValueError('Cannot package incomplete actual stages: '+repr(absent))
 validate_actual_audits(work)
 primary_report=work/'checks/medical_primary_scope_actual.json'
 if primary_report.is_file():validate_primary_scope_report(primary_report)
 population=json.loads((work/'population_context_readout/summary.json').read_text())
 if len(population.get('tables',{}))!=15 or not population.get('no_population_budgets_or_assignments_changed'):raise ValueError('Incomplete nonadditive city population readout')
 if not {'medical_basic_primary','school_general','daily_grocery'}.issubset(route_view(work)):raise ValueError('Required daily raw source classes missing')


def copy_reproduction(local):
 root=local/'reproduction'
 for folder in ['scripts/sgrt_zero','scripts/sgrt_mass','sgrt/zero']:
  if (REPO/folder).exists():shutil.copytree(REPO/folder,root/folder,ignore=shutil.ignore_patterns('__pycache__'))
 for filename in ['scripts/sgrt_pilot/package_release.py','scripts/research_data.py','data/catalog.json',
                  'data/pilot_catalog_20261024.json','data/mass_catalog_20261024.json','references/sources.json','references/usage.json',
                  'research_context/primary/word_concept_extracted.txt','research_context/primary/word_concept.docx','research_context/current_state.json',
                  'research_context/analysis_snapshots/zero_controls_20261025.json','research_context/conversation_context_20261025.md',
                  'research_context/conversation_context_20261022.md','decisions.json','AGENTS.md','README.md','AI_START_HERE.md',
                  'requirements-sgrt-pilot.txt','requirements-sgrt-mass-centres.txt','requirements-sgrt-mass.txt','requirements-sgrt-zero.txt']:
  source=REPO/filename
  if source.exists():copy_file(source,root/filename)
 diary=REPO/'research_context/diary'
 if diary.exists():
  latest=sorted(diary.glob('20??-??-??.md'))[-1:]
  for p in latest:copy_file(p,root/'research_context/diary'/p.name)


def result_readme(work,commit):
 """Explain the completed calculation from its actual summaries, not source-time prose."""
 checks=json.loads((work/'checks/scientific_checks.json').read_text())
 main=SCENARIOS[0]
 rows=[]
 for scenario in SCENARIOS:
  value=json.loads((work/'hierarchy'/scenario/'summary.json').read_text())
  rows.append((scenario,value['level0_units'],value['inhabited_multi_np_service_areas']))
 strict=json.loads((work/'upward'/main/'summary.json').read_text())['stages']
 extended=json.loads((work/'upward_extended'/main/'summary.json').read_text())['scenarios']
 scenario_names={
  'daily_20_school30_wb':'Основной: медицина и магазины 20 минут, школа 30 минут, Wildberries',
  'daily_10_school15_wb':'Более близкое обслуживание: медицина и магазины 10 минут, школа 15 минут, Wildberries',
  'daily_30_school30_wb':'Более широкий вариант: медицина, магазины и школа 30 минут, Wildberries',
  'core3_20_school30':'Три основные услуги: медицина и магазины 20 минут, школа 30 минут, без ПВЗ',
  'daily_20_school30_yandex':'Те же основные пределы: медицина и магазины 20 минут, школа 30 минут, Яндекс Маркет'}
 stage_names={
  'physician_direct_30':'Врачебная помощь, до 30 минут',
  'urban_hospital_college':'Стационар и профессиональное образование, до 90 минут',
  'urban_specialized_university_shopping':'Специализированная помощь, вузы и крупные торговые центры, до 90 минут',
  'urban_hightech':'Высокотехнологичная медицинская помощь, до 120 минут'}
 mode_names={'all_declared':'Все требуемые функции подтверждены для целых нижних групп',
  'partial_positive_two_domains':'Не менее двух подтверждённых сфер для целых нижних групп; остальные сведения могут отсутствовать'}
 n=lambda value:f'{int(value):,}'.replace(',',' ')
 lines=['# Результат завершённого расчёта','',
  f'Основной вариант выделил **{n(rows[0][2])} групп с двумя и более населёнными НП**. '
  'Это модельные местные группы по ближайшим известным услугам. Реальные поездки и окончательные СГРТ этим ещё не установлены.','',
  f'В расчёте {n(checks["analysis_origins"])} исходных точек: '
  f'{n(checks["ordinary_origins"])} обычных НП и {n(checks["nonadditive_context_origins"])} отдельных городских контекста. '
  'Москва, Петербург и Севастополь участвуют как центры; их справочное население не прибавляется к сумме обычных НП.','',
  'Численность населения не определяет преимущество центра на нулевом уровне. '
  'Группа объединяет точки с одинаковым набором выбранных поставщиков; неизвестные услуги сохраняются неизвестными. '
  'Часть групп состоит из одной точки, поэтому общее число групп нельзя выдавать за число местных многопоселенческих систем.','',
  '| Вариант | Все группы, включая одиночные | Группы с двумя и более населёнными НП |',
  '| --- | ---: | ---: |']
 for scenario,units,multi in rows:lines.append(f'| {scenario_names.get(scenario,scenario)} | {n(units)} | {n(multi)} |')
 lines += ['', 'Правила вариантов раскрыты в `reproduction/sgrt/zero/METHOD.md`: '
  'меняются пределы близкого обслуживания и отдельный оператор выдачи заказов. '
  'Основной вариант использует 20 модельных минут для базовой медицины и магазинов, '
  '30 для школы; это исследовательские допущения, а не оценка фактических поездок.','',
  '## Более крупные объединения','',
  'Каждая следующая группа состоит из целых нижних групп. Для каждого участника проверяется '
  'прямая доступность нового поставщика; цепочка соседств не даёт права бесконечно расширять ареал.','',
  '| Новый набор услуг | Групп после шага | Новых объединений |', '| --- | ---: | ---: |']
 for stage in strict:lines.append(f'| {stage_names.get(stage["name"],stage["name"])} | {n(stage["parent_units"])} | {n(stage["new_merger_groups"])} |')
 lines += ['', 'Для сравнения рассчитаны два варианта выхода за внешний контур агломерации 2015 года. '
  'Во всех случаях сохраняются ограничения прямой доступности и целостность нижних групп.','',
  '| Вариант | Последний проверенный шаг | Итоговое число групп | Новых объединений на последнем шаге |',
  '| --- | --- | ---: | ---: |']
 for mode,stages in extended.items():
  last=stages[-1]
  lines.append(f'| {mode_names.get(mode,mode)} | {stage_names.get(last["name"],last["name"])} | {n(last["parent_units"])} | {n(last["new_merger_groups"])} |')
 lines += ['', '**Число шагов объединения не является рангом города.** '
  'Уровень, на который поднимается исключительно Москва, этими расчётами не установлен. '
  'Он не создаётся искусственно из численности населения или лишних пустых ступеней.','',
  '## Источники и смысл результата','',
  '- Население: связанная база переписей 2002, 2010 и 2021 годов; исходная база не изменена.',
  '- Медицина: федеральные справочники ОМС на 23 октября 2026 года, датированные региональные сведения, OSM. '
  'Исторические записи не объявляются подтверждением нынешней работы. Детский и специальный контингент выделен отдельно.',
  '- Образование: объекты OSM 2026 года и сохранённые официальные сведения. '
  'Не у каждого объекта установлена принадлежность к конкретному НП; координатный объект всё равно может участвовать в дорожном поиске.',
  '- Магазины: OSM 2021 года и свежие положительные сведения о продуктовых магазинах при 5Post. '
  'Пункты выдачи Wildberries, Яндекс Маркета и 5Post сохранены отдельно; операторы не считаются дополнительными независимыми функциями.',
  '- Дороги: сохранённый граф OSM 2021 года. Время является модельной автомобильной стоимостью, а не наблюдённой длительностью поездки.',
  '- Внешние контуры: исследовательская оценка eFUA/GHSL/JRC 2015 года, а не доказанные современные границы агломераций.',
  '- Работники и сельское хозяйство: контекстные таблицы. Районные посевы не распределены по деревням; '
  'частичная численность работников организаций не объявляется полным числом рабочих мест.','',
  'Отсутствие записи не означает отсутствия учреждения. Наличие лицензии не означает поток пациентов или пригодность для любой медицинской потребности. '
  'Редкая помощь учитывается по отдельным заявленным профилям; подходящая больница для каждого жителя не установлена. '
  'Федеральный охват не доказывает полноту инвентаря.','',
  '## Как проверить и продолжить','',
  'Сначала смотрите `figures/zero_level_atlas.pdf`, затем таблицы `hierarchy/`, `upward/` и `upward_extended/`. '
  'В `checks/` находятся численные проверки фактического результата; в `population_context_readout/` — отдельное пояснение городского населения. '
  'При наличии федеральных свидетельств `functional_complexity/` описывает известные функции, не присваивая неподтверждённого ранга.','',
  '`checksums.json` проверяет все файлы; `logical_source_roles.json` указывает точный источник каждой таблицы. '
  '`reproduction/` содержит код, концепцию, контекст, дневник и литературу. Компактный пересчёт заново строит группы и карты из сохранённых дорожных направлений.','',
  f'Исходный коммит кода: `{commit}`. Точные суммы скопированного кода — в `source_code_state.json`. '
  '**Тексты в `reproduction/research_context/` отражают состояние на момент исходного коммита.** '
  'Если там ещё указан запуск расчёта, состояние завершённого результата описывает настоящий файл, созданный после всех вычислений из фактических итоговых таблиц.','']
 return '\n'.join(lines)


def package(work,tag,commit):
 work=Path(work);check_complete(work)
 if not re.fullmatch('[0-9a-fA-F]{40}',commit):raise ValueError('Complete source commit SHA required')
 if not re.fullmatch('sgrt-zero-systems-20261025-v[0-9]+',tag):raise ValueError('Unexpected result tag')
 # Scientific completeness is checked before an old local build is removed.
 payload=work/'payload';built=work/'built'
 if payload.exists():shutil.rmtree(payload)
 if built.exists():shutil.rmtree(built)
 local=payload/PREFIX;local.mkdir(parents=True);built.mkdir()
 selected=payload_files(work);before={rel:digest(path) for rel,path in selected.items()}
 for rel,path in selected.items():copy_file(path,local/rel)
 if before!={rel:digest(path) for rel,path in selected.items()}:raise RuntimeError('Scientific data changed during packaging')
 for rel,sha in before.items():
  if digest(local/rel)!=sha:raise RuntimeError('Copied scientific data differ: '+rel)
 source_roles={rel:{'source_path':str(path),'sha256':before[rel]} for rel,path in selected.items()}
 (local/'logical_source_roles.json').write_text(json.dumps(source_roles,ensure_ascii=False,indent=2)+'\n')
 copy_reproduction(local)
 (local/'RESULT_README.md').write_text(result_readme(work,commit),encoding='utf-8')
 code_files={p.relative_to(local/'reproduction').as_posix():digest(p) for p in (local/'reproduction/scripts').rglob('*.py')}
 code_state={'declared_source_commit':commit,'actual_copied_python_sha256':code_files,
  'commit_is_a_declared_anchor_actual_file_hashes_are_authoritative':True}
 (local/'source_code_state.json').write_text(json.dumps(code_state,ensure_ascii=False,indent=2)+'\n')
 (local/'README.txt').write_text('Нулевой уровень: группы по ближайшим повседневным услугам; верхние объединения — явные ограниченные сценарии.\n'
  'Связи не являются наблюдёнными поездками. Переписная база неизменна.\n'
  'Компактный режим заново считает допуски, пять вариантовL0, четыре новых функциональных набора, проверки и карты из сохранённых дорожных направлений.\n'
  f'Объявленный коммит: {commit}. Точные SHA скопированного кода: source_code_state.json.\n',encoding='utf-8')
 checksums={p.relative_to(local).as_posix():digest(p) for p in sorted(local.rglob('*')) if p.is_file()}
 (local/'checksums.json').write_text(json.dumps(checksums,ensure_ascii=False,indent=2)+'\n')
 helper=REPO/'scripts/sgrt_pilot/package_release.py'
 spec=importlib.util.spec_from_file_location('zero_portable_package_helper',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 module.package(payload,built,tag,commit)
 (built/'sgrt-pilot-data.zip').rename(built/'zero-data.zip')
 cat=json.loads((built/'pilot_catalog.json').read_text());archive=built/'zero-data.zip'
 for row in cat['files']:row['asset']=archive.name
 for obj in cat['objects'].values():obj['asset']=archive.name
 cat['assets'][0].update(asset=archive.name,url='https://github.com/'+cat['repository']+'/releases/download/'+tag+'/'+archive.name)
 cat['profiles']={'core':'Complete explicitly selected zero-level companion bundle','all':'Same companion files'}
 cat['scientific_scope']='National conditional daily-service profiles and explicitly bounded higher functional scenarios; source gaps retained, no observed travel claim or forced Moscow-only top.'
 content=json.dumps(cat,ensure_ascii=False,indent=2)+'\n'
 if len(content.encode())>950_000:
  for obj in cat['objects'].values():obj.pop('fields',None)
  content=json.dumps(cat,ensure_ascii=False,indent=2)+'\n'
 if len(content.encode())>950_000:content=json.dumps(cat,ensure_ascii=False,separators=(',',':'))+'\n'
 if len(content.encode())>950_000:raise ValueError('Companion catalogue exceeds compact Git budget')
 (built/'zero_catalog.json').write_text(content);(built/'pilot_catalog.json').unlink()
 copy_file(work/'figures/zero_level_atlas.pdf',built/'zero_atlas.pdf')
 copy_file(work/'figures/01_national_statuses.png',built/'preview.png')
 return cat


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--workdir',type=Path);p.add_argument('--source-commit');p.add_argument('--tag',default=TAG)
 p.add_argument('--source-manifest-sha256',default=SOURCE_MANIFEST_SHA256)
 p.add_argument('--plan',action='store_true');p.add_argument('--prepared',action='store_true');p.add_argument('--package-only',action='store_true')
 p.add_argument('--from-bundle',type=Path);a=p.parse_args()
 if a.plan:print(json.dumps(plan(),ensure_ascii=False,indent=2));return
 if a.workdir is None or not a.source_commit:p.error('--workdir and --source-commit required')
 if a.prepared and a.from_bundle:p.error('Choose prepared or from-bundle, not both')
 if not re.fullmatch('[0-9a-fA-F]{40}',a.source_commit):p.error('Complete source commit SHA required')
 work=a.workdir.resolve();work.mkdir(parents=True,exist_ok=True)
 if not a.package_only:
  if a.from_bundle:compact_prepare(a.from_bundle,work)
  elif not a.prepared:full_prepare(work,a.source_manifest_sha256)
  analyses(work)
 cat=package(work,a.tag,a.source_commit)
 print(json.dumps({'catalog':str(work/'built/zero_catalog.json'),'counts':cat['counts'],'archive_bytes':cat['assets'][0]['bytes']}))


if __name__=='__main__':main()
