#!/usr/bin/env python3
"""Rebuild portable error evidence and corrected metadata on frozen v1 groups.

No service rerouting or new SGRT partition is performed. Source reassessments
and group descriptions are kept in separate namespaces from published v1.
"""
import argparse,hashlib,json,shutil,subprocess,sys,zipfile
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
TAG='sgrt-semantic-audit-20261025-v1'


def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(4<<20),b''):h.update(block)
 return h.hexdigest()


def build(bundle,work,commit):
 from scripts.sgrt_zero.reproduce import verify_bundle
 if work.exists() and any(work.iterdir()):raise ValueError('Choose an empty audit workdir')
 work.mkdir(parents=True,exist_ok=True);out=work/'audit';out.mkdir();logs=out/'logs';logs.mkdir()
 before=verify_bundle(bundle);script=REPO/'scripts/sgrt_zero';ref=bundle/'context/analysis_reference.parquet';inp=bundle/'inputs'
 def run(label,name,*args):
  logpath=logs/(label+'.log')
  try:
   with logpath.open('w') as log:
    subprocess.run([sys.executable,str(script/name),*map(str,args)],check=True,stdout=log,stderr=subprocess.STDOUT,cwd=REPO)
  except subprocess.CalledProcessError:
   print('\n'.join(logpath.read_text(errors='replace').splitlines()[-50:]),flush=True)
   raise
  print(label,flush=True)
 run('profile_grain','lower_profile_quality.py','--directory',bundle/'hierarchy/daily_20_school30_wb','--reference',ref,'--output',out/'profile_quality')
 run('group_metadata','type_readout.py','--root',bundle,'--output',out/'group_metadata')
 run('old_education_choices','diagnose_public_education.py','--bundle',bundle,'--output',out/'education_diagnostics')
 education=work/'education_rebuilt'
 run('education_reassessment','education.py','--current',inp/'education_current.parquet','--historical',inp/'education_history.parquet','--official',inp/'preschool.parquet','--reference',ref,'--legacy',inp/'legacy.parquet','--city-context',bundle/'context/city_context_origins.parquet','--output',education)
 run('education_change_impact','compare_public_education_revision.py','--bundle',bundle,'--revision',education,'--output',out/'education_changes')
 # Rebuild primary source support, including the new same-year exact-unit evidence.
 health=work/'health_rebuilt';strict=work/'health_strict';legacy=work/'health_legacy';functions=work/'federal_functions';codes=work/'codebooks';codes.mkdir()
 archive=inp/'frozen_federal_medical/SpravNSI_20261023.zip'
 with zipfile.ZipFile(archive) as z:
  for code in ['V002','V006','V008']:
   names=[n for n in z.namelist() if Path(n).name==code+'.xml']
   if len(names)!=1:raise ValueError('Ambiguous source codebook '+code)
   with z.open(names[0]) as src,(codes/(code+'.xml')).open('wb') as dst:shutil.copyfileobj(src,dst)
 run('health_reassessment','health.py','--osm-current',inp/'health_current.parquet','--osm-history',inp/'health_history.parquet','--official-supply',inp/'licensed_supply.parquet','--official-sites',inp/'licensed_sites.parquet','--reference',ref,'--legacy',inp/'legacy.parquet','--output',health)
 run('health_public_scope','health.py','correct-public-scope','--health-root',health,'--official-supply',inp/'licensed_supply.parquet','--official-sites',inp/'licensed_sites.parquet','--reference',ref,'--output',strict)
 run('federal_clinical_scope','federal_medical_functions.py','--input',bundle/'federal_medical/normalized/care_site_profiles_current.parquet','--codebooks',codes,'--asof','2026-10-23','--output',functions)
 run('legacy_clinical_scope','medical_scope.py','--base-health',strict,'--legacy-sites',inp/'licensed_sites.parquet','--legacy-supply',inp/'licensed_supply.parquet','--reference',ref,'--federal-care-ledger',bundle/'federal_medical/normalized/care_site_profiles_current.parquet','--output',legacy)
 integrated=work/'health_integrated'
 run('medical_integrate','federal_medical_integrate.py','--classified',functions/'care_rows_classified.parquet','--evidence',functions/'service_evidence_by_care_address.parquet','--addresses',bundle/'federal_medical/addresses/F038_current_np_identity.parquet','--reference',ref,'--base-health',legacy,'--historical-supplement',bundle/'health/saratov_2021_supplement','--output',integrated)
 run('medical_change_impact','diagnose_public_medical.py','--root',bundle,'--after-health',integrated,'--after-functions',functions,'--after-legacy',legacy,'--output',out/'medical_diagnostics')
 run('commerce_access','diagnose_commerce_access.py','--root',bundle,'--output',out/'commerce_diagnostics')
 run('provider_aliases','audit_transport_selected_contract.py','--bundle',bundle,'--output',out/'transport_contract')
 after=verify_bundle(bundle)
 if before!=after:raise ValueError('The frozen input bundle changed')
 for folder in ['scripts/sgrt_zero','scripts/sgrt_mass','research_context/analysis_snapshots']:
  shutil.copytree(REPO/folder,out/'reproduction'/folder,ignore=shutil.ignore_patterns('__pycache__'))
 for name in ['README.md','AGENTS.md','requirements-sgrt-zero.txt','research_context/current_state.json','research_context/diary/2026-10-25.md','sgrt/zero/ERROR_AUDIT_20261025.md']:
  target=out/'reproduction'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/name,target)
 text=('Аудит ошибок сервисных профилей. 25 октября 2026 года.\n\n'
 'Комплект содержит свидетельства ошибок, переоценку источников и новые описания 15 неизменных разделений выпуска v1. '
 'Новые направления и территории после удаления неподходящих поставщиков не пересчитаны. '
 'Это не готовый исправленный нулевой уровень СГРТ.\n\n'
 'Содержимое:\n'
 '- group_metadata: 15 таблиц единиц и 15 таблиц центра и окружения;\n'
 '- profile_quality: части НП, совпавшие координаты и внешние центры;\n'
 '- education_changes: исправленные назначения и область перевыбора;\n'
 '- medical_diagnostics: подтверждения, спорные случаи и сохранность функций;\n'
 '- commerce_diagnostics: явные ограничения доступа;\n'
 '- transport_contract: согласование идентификаторов без изменения минут.\n\n'
 'Кандидатные записи review не равны доказанным ошибкам. Первичные данные находятся в sgrt-zero-systems-20261025-v1. '
 'Повторение: semantic_audit_bundle.py --bundle PATH --workdir EMPTY --source-commit SHA.\n')
 (out/'README.txt').write_text(text,encoding='utf-8')
 files={p.relative_to(out).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.rglob('*')) if p.is_file()}
 manifest={'release_tag':TAG,'source_commit':commit,'input_release':'sgrt-zero-systems-20261025-v1','frozen_input_files_verified_before_and_after':before,'source_inputs_unchanged':True,'routing_recomputed':False,'v1_memberships_changed':False,'not_a_corrected_sgrt_partition':True,'files':files}
 (out/'audit_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 built=work/'built';built.mkdir();target=built/'semantic-audit.zip'
 with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(out.rglob('*')):
   if p.is_file():z.write(p,arcname='sgrt/semantic_audit20261025/'+p.relative_to(out).as_posix())
 manifest['archive']={'asset':target.name,'bytes':target.stat().st_size,'sha256':sha(target)}
 (built/'audit_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 shutil.copyfile(out/'README.txt',built/'README.txt')
 return manifest


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',required=True,type=Path);p.add_argument('--workdir',required=True,type=Path);p.add_argument('--source-commit',required=True);a=p.parse_args()
 actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
 if len(a.source_commit)!=40 or actual!=a.source_commit:raise ValueError('Use the exact current source commit')
 if subprocess.run(['git','diff','--quiet','HEAD'],cwd=REPO).returncode:
  raise ValueError('Commit source and context changes before building an immutable audit')
 if subprocess.check_output(['git','ls-files','--others','--exclude-standard','scripts/sgrt_zero','scripts/sgrt_mass'],cwd=REPO,text=True).strip():
  raise ValueError('Untracked scientific source must be committed before packaging')
 if a.workdir.resolve().is_relative_to(REPO):raise ValueError('Keep generated audit data outside the source repository')
 sys.path.insert(0,str(REPO));result=build(a.bundle.resolve(),a.workdir.resolve(),a.source_commit);print(json.dumps({'archive':result['archive'],'files':len(result['files'])}))
