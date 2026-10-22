#!/usr/bin/env python3
"""Freeze sidecars after the actual screening and retail construct audit."""
from pathlib import Path
import datetime,hashlib,json,sys
import numpy,pandas,pyarrow
R=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 a=json.loads((R/'SCREENING_AUDIT.json').read_text());r=json.loads((R/'RETAIL_CONSTRUCT_AUDIT.json').read_text());receipt=json.loads((R/'ACTUAL_COMMAND_RECEIPT.json').read_text());assert a['pass'] and r['pass'] and sha(R/'support_point_profiles.parquet')==receipt['output_sha256']
 dump(R/'SOURCE_COLUMN_BINDINGS_SUPPLEMENT.json',{'retail_source_interpretation':{'source':'national_integration_20261019/places/places_objects_and_crosswalk.parquet','columns':['function_group','source_category','name_signal_wildberries','name_signal_ozon','baseline_uid','conditional_uid','nearest_uid_unaccepted','source_geography_scope','country_polygon_conflict','source_operating_status'],'scope':'scope eligible, no country conflict, no permanently_closed; unknown retained as unknown','exclusion_rule':'Only function_group=retail_store AND source_category=shopping AND (name_signal_wildberries OR name_signal_ozon)','DoctorOzon':'healthcare not transformed into pickup and not excluded','retail_RFSD':'never removed by POI name sensitivity'},'primary11':'retail OR marketplace_pickup -> trade_access; all other 10 broad groups preserved','unmerged12':'explicit *_unmerged_* source/profile sensitivity','not_measured':['external catchments','physical service closure','complete facility inventory','support priority or irreplaceability']})
 dump(R/'RUNTIME_VERSIONS.json',{'python':sys.version,'numpy':numpy.__version__,'pandas':pandas.__version__,'pyarrow':pyarrow.__version__})
 text=(R/'README.md').read_text();marker='\n## Дополнительная холодная проверка конструкции\n'
 if marker in text:text=text[:text.index(marker)]
 text+=marker+'''
`RETAIL_CONSTRUCT_AUDIT.json`: 9/9 дополнительных авторских проверок PASS. По исходному POI-long независимо от широких счётчиков восстановлены 53 434 baseline /79 494 conditional-full retail записи. Retail-name исключение затрагивает11 /9 597 принятых записей; основной11-групповой baseline не меняет категорию ни одного НП, conditional меняет828. Консолидация retail+pickup меняет multiple→single у1 675 /3 171 НП. Независимая агентская валидация хранится отдельно от этих авторских проверок.

```bash
python3 national_integration_20261019/screening/validate_retail_sensitivity.py
python3 national_integration_20261019/screening/finalize_screening_metadata.py
```

Общий итог автора:20 основных инвариантов и9 дополнительных холодных проверок PASS. `SOURCE_COLUMN_BINDINGS_SUPPLEMENT.json` фиксирует точные входные колонки сценария. `FREEZE.json` фиксирует неизменяемые хеши данных; `MANIFEST.json` включает все завершённые sidecar-файлы. После freeze таблицы не менялись.
''';(R/'README.md').write_text(text)
 dump(R/'FREEZE.json',{'frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rows':a['rows'],'columns':a['columns'],'primary_function_count':a['primary_function_count'],'unmerged_function_count':a['unmerged_function_count'],'author_main_checks':len(a['checks']),'author_retail_construct_checks':len(r['checks']),'independent_validation_is_separate':True,'data_files':{f:{'sha256':sha(R/f),'bytes':(R/f).stat().st_size} for f in ['support_point_profiles.parquet','support_point_profiles.csv.gz','evidence_change_review_queue.parquet','source_bundle_disagreements.parquet']},'source_inputs':a['inputs']})
 dump(R/'MANIFEST.json',{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(R.iterdir()) if p.is_file() and p.name!='MANIFEST.json'})
 print(json.dumps({'rows':a['rows'],'columns':a['columns'],'main_checks':len(a['checks']),'retail_checks':len(r['checks']),'closed_sha256':receipt['output_sha256']}))
if __name__=='__main__':main()
