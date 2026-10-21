from pathlib import Path
import hashlib,json,runpy
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');D=B/'delivery/cycle07_tools';O=B/'reviews/cycle07_report_v7_prospective_independent';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=D/'tooling_freeze_manifest_v7.json';before={str(manifest):sha(manifest)};data=json.loads(manifest.read_text())
for f,h in data['files'].items():assert sha(D/f)==h;before[str(D/f)]=h
code=(D/'test_report_v7.py').read_text().replace("HERE/'synthetic_report_checks_v7.json'", "Path('/tmp/cycle07_report_v7_independent_synthetic_checks.json')")
ns={'__file__':str(D/'test_report_v7.py'),'__name__':'__independent_synthetic__'};exec(compile(code,str(D/'test_report_v7.py'),'exec'),ns)
for p,h in before.items():assert sha(p)==h,('Frozenfilechanged',p)
r=json.loads(Path('/tmp/cycle07_report_v7_independent_synthetic_checks.json').read_text());(O/'synthetic_rerun_receipt.json').write_text(json.dumps({'status':'INDEPENDENT_RERUN_SYNTHETIC_ONLY_NO_ACTUAL_REPORT_ACCEPTANCE','all_checks_passed':all(r['checks'].values()),'n_checks':len(r['checks']),'builder_sha256':sha(D/'build_report_v7.py'),'frozenfiles_before_after_exact':before,'synthetic_result':r},ensure_ascii=False,indent=2)+'\n');print('FROZEN_BEFORE_AFTER_EXACT',len(r['checks']))
