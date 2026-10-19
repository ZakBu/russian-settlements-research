"""Freeze, cold-read and package the complete new wave with required inputs.

ZIP parts are independent archives; extract all to the same directory. The
older 63M-row calendar is a frozen input, not reconstructed by this wave.
"""
from pathlib import Path
import hashlib,json,os,shutil,zipfile,time
import pyarrow.parquet as pq
import pandas as pd
R=Path(__file__).resolve().parent;B=R.parent;D=B/'national_deliverables_20261019'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def good(p):
 rel=p.relative_to(R);s=rel.as_posix()
 return p.is_file() and not any(x.startswith('.') or x=='__pycache__' for x in rel.parts) and not s.startswith(('core/results/','output/qa/')) and not p.name.startswith('INITIAL_WITHOUT_PLACES_') and not p.name.endswith(('.partial','.corrupt_preserved','.previous_preserved','.body.pdf','.pyc','.npy')) and p.name not in {'ARTIFACT_MANIFEST.json','PACKAGE_AUDIT.json','PACKAGE_PARQUET_READBACK.json'}
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def zipped(path,files):
 with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True)as z:
  for p in sorted(files):z.write(p,p.relative_to(B).as_posix())
 # Full streamed hash validation; no successful central directory alone suffices.
 with zipfile.ZipFile(path)as z:
  for n in z.namelist():
   h=hashlib.sha256()
   with z.open(n)as f:
    for b in iter(lambda:f.read(2**20),b''):h.update(b)
   assert h.hexdigest()==sha(B/n),('archive content differs',n)
def main():
 start=time.monotonic();D.mkdir(exist_ok=True);replay=json.loads((R/'REPLAY.json').read_text());assert replay['status']=='PASS' and len(replay['commands'])==12 and len(replay['comparisons'])==16
 assert all(x['all_typed_cells_and_nulls_exact']for x in replay['comparisons'])
 included={p for p in R.rglob('*')if good(p)}
 inputs={Path(p)for p in replay['frozen_input_sha256_before']}
 for p,h in replay['frozen_input_sha256_before'].items():assert sha(p)==h,('frozen input changed',p)
 extra=['restored/extracted/inputs/recovery_inputs/columnar/agriculture.parquet','restored/extracted/inputs/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz','anchor_research_20261019/literature/SOURCE_MATRIX.csv','anchor_research_20261019/literature/RECOMMENDED_METHOD.md','anchor_research_20261019/literature/ACQUISITION_AND_READING.json']
 inputs.update(B/p for p in extra)
 allfiles=included|inputs;assert all(p.is_file()for p in allfiles)
 source=B/extra[1];assert sha(source)=='d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c'
 original=pd.read_csv(source,low_memory=False);assert original.shape==(142570,135);del original
 # Every included parquet is fully decoded in bounded batches after the large
 # write incidents, not merely inspected at its footer.
 reads=[]
 for p in sorted(allfiles):
  if p.suffix!='.parquet':continue
  pf=pq.ParquetFile(p);rows=0
  for batch in pf.iter_batches(batch_size=8192,use_threads=False):rows+=batch.num_rows
  assert rows==pf.metadata.num_rows
  reads.append({'path':p.relative_to(B).as_posix(),'rows':rows,'columns':len(pf.schema_arrow.names),'sha256':sha(p)})
 dump(R/'PACKAGE_PARQUET_READBACK.json',{'status':'PASS','all_columns_decoded_in_bounded_batches':True,'files':reads})
 included.add(R/'PACKAGE_PARQUET_READBACK.json');allfiles.add(R/'PACKAGE_PARQUET_READBACK.json')
 manifest={p.relative_to(B).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p),'kind':'frozen_input'if p in inputs else'new_wave_artifact'}for p in sorted(allfiles)}
 dump(R/'ARTIFACT_MANIFEST.json',{'scope':'Complete new-wave calculations with required frozen prior inputs; raw15year RFSD acquisition is in the previous full delivery','files':manifest})
 included.add(R/'ARTIFACT_MANIFEST.json');allfiles.add(R/'ARTIFACT_MANIFEST.json')
 # Small direct downloads.
 copies={'SGRT_NATIONAL_FUNCTIONS_REPORT.pdf':R/'output/pdf/SGRT_NATIONAL_FUNCTIONS_REPORT.pdf','SGRT_NATIONAL_FUNCTIONS_BRIEF.pdf':R/'output/pdf/SGRT_NATIONAL_FUNCTIONS_BRIEF.pdf','SGRT_NATIONAL_FEATURE_MASTER.parquet':R/'core/feature_master.parquet','SGRT_NATIONAL_FEATURE_MASTER.csv.gz':R/'core/feature_master.csv.gz','SGRT_NATIONAL_FUNCTION_PROFILES.parquet':R/'screening/support_point_profiles.parquet','SGRT_NATIONAL_FUNCTION_PROFILES.csv.gz':R/'screening/support_point_profiles.csv.gz','SGRT_FUNCTIONS_RUSSIA.png':R/'figures/01_function_profiles.png','claim_registry.csv':R/'claim_registry.csv','BIBLIOGRAPHY.md':R/'BIBLIOGRAPHY.md'}
 for n,p in copies.items():shutil.copy2(p,D/n);assert sha(D/n)==sha(p)
 maps={p for p in included if p.parent==R/'figures' and p.suffix in {'.png','.svg','.pdf','.csv','.json'}};zipped(D/'SGRT_NATIONAL_MAPS.zip',maps)
 results={p for p in included if not p.relative_to(R).as_posix().startswith(('places/selected/','places/metadata/','places/documentation/','replay_logs/')) and p.name not in {'places_objects_and_crosswalk.parquet','places_objects_and_crosswalk.csv.gz','places_external_geography.parquet'}}
 zipped(D/'SGRT_NATIONAL_RESULTS.zip',results)
 # First-fit decreasing, <=480MiB uncompressed so each compressed part remains
 # below the512MiB per-file transport ceiling even on incompressible members.
 cap=480*2**20;bins=[]
 for p in sorted(allfiles,key=lambda p:p.stat().st_size,reverse=True):
  size=p.stat().st_size;assert size<=cap
  for bucket in bins:
   if bucket['bytes']+size<=cap:bucket['files'].append(p);bucket['bytes']+=size;break
  else:bins.append({'bytes':size,'files':[p]})
 parts=[]
 for i,bucket in enumerate(bins,1):
  p=D/f'SGRT_NATIONAL_REPRODUCIBLE_PART_{i}.zip';zipped(p,bucket['files']);assert p.stat().st_size<512*2**20
  parts.append({'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p),'uncompressed_bytes':bucket['bytes'],'members':[f.relative_to(B).as_posix()for f in sorted(bucket['files'])]})
 dump(D/'ARCHIVE_PARTS_MANIFEST.json',{'parts':parts,'total_members':len(allfiles),'extract_all_to_same_directory':True,'concatenation_required':False,'every_member_sha_verified':True})
 (D/'RUN_INSTRUCTIONS.txt').write_text('''СГРТ: ПОЛНАЯ НАЦИОНАЛЬНАЯ ИНТЕГРАЦИЯ19.10.2026

Для чтения достаточно PDF и таблиц результатов. Полная база142570строк/914полей; профиль448полей. Это каталог свидетельств, не доказанные границыСГРТ.

Для автономного повтора новой волны распакуйте ВСЕ SGRT_NATIONAL_REPRODUCIBLE_PART_*.zip в ОДНУ папку. Это самостоятельныеZIP; склеивать не нужно. Рядом окажутся national_integration_20261019/, anchor_research_20261019/, functional_dynamics_20261019/ иrestored/ с нужными закреплёнными входами.

Из общего рабочего корня наLinux сPython3.12:
python -m pip install -r national_integration_20261019/requirements.txt
python national_integration_20261019/replay_all.py

Фактически выполнено12команд,16полныхтипизированныхсравнений,308.058секунды. Форматныебайты2файловмогу́тотличатьсяприравенствевсехзначений/типов/null. Все34замороженныхвходныхSHAсохранены. ЧитайтеREPLAY.json.

Дополнительные таблицы отчёта:
python national_integration_20261019/build_report_tables.py
python national_integration_20261019/build_national_report.py
python national_integration_20261019/build_figures.py
python national_integration_20261019/render_reports.py

Пакет содержит входы ДЛЯ ЭТОЙ ВОЛНЫ, включая ранее рассчитанный15-летнийRFSD-календарь. Он не объявляется повтором первоначального получения63млнRFSD-строк: полный прежний исходный комплект и27-командный replay переданы отдельно. Новые финансовые2016/2021 и физическиеPlaces вэтойволне действительнопересчитываются.

ARTIFACT_MANIFEST.json внутри исследования —SHA всех файлов; ARCHIVE_PARTS_MANIFEST.json — состав частей; CHECKSUMS.json —SHA прямых скачиваемых файлов. Исходныйstage71добавлен неизменным и повторно проверен(142570×135).
''',encoding='utf-8')
 checks={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)}for p in sorted(D.iterdir())if p.is_file()and not p.name.startswith('.')and p.name!='CHECKSUMS.json'};dump(D/'CHECKSUMS.json',checks)
 audit={'status':'PASS','parquet_files_fully_read':len(reads),'new_wave_files':len(included),'all_repro_members':len(allfiles),'archive_parts':len(parts),'archive_members_hash_verified':True,'stage71_shape':[142570,135],'seconds':round(time.monotonic()-start,3)}
 dump(R/'PACKAGE_AUDIT.json',audit);print(json.dumps(audit))
if __name__=='__main__':main()
