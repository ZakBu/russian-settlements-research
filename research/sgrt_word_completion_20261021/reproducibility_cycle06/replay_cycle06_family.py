"""Actually rerun the frozen national model and compare all declared model outputs."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parents[1]

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model-output',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--receipt-directory',type=Path,required=True)
    args=parser.parse_args()
    original=args.model_output.resolve()
    output=args.output.resolve()
    report=args.receipt_directory.resolve()
    report.mkdir(parents=True,exist_ok=True)
    if (output/'run_receipt.json').exists():
        raise FileExistsError('Fresh replay requires a new output directory')
    manifest = original / 'output_manifest.json'
    spec = json.loads(manifest.read_text())
    code = ROOT / 'model/run_word_model_cycle06.py'
    config = REPO / spec['configuration_path']
    required={'run_word_model_cycle06.py','large_city_accessibility_cycle05.py','configuration_cycle06.py'}
    if set(spec['execution_source_snapshots'])!=required:raise ValueError('All three execution sources must be pinned')
    for name,item in spec['execution_source_snapshots'].items():
        assert sha(ROOT/'model'/name)==item['sha256']
        assert sha(REPO/item['path'])==item['sha256']
    for name,item in spec['files'].items():
        if sha(original/name)!=item['sha256']:raise ValueError('Original artifact changed: '+name)
    assert sha(code) == spec['model_code_sha256']
    assert sha(config) == spec['configuration_sha256']
    command = [sys.executable, str(code.relative_to(REPO)), '--inputs',
               str(config.relative_to(REPO)), '--output', str(output), '--stage', 'full']
    protocol = {'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'command': command, 'original_manifest_sha256': sha(manifest),
                'code_sha256': sha(code), 'configuration_sha256': sha(config),
                'acceptance': 'Every frozen substantive output must exactly match bytes; run receipt only runtime may differ',
                'scientific_geometry_validation': False}
    (report / 'full_replay_protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    env = os.environ.copy()
    env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    start = time.monotonic()
    with (report / 'full_replay.log').open('wb') as log:
        result = subprocess.run(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
    checks = []
    if result.returncode == 0:
        for name, item in spec['files'].items():
            actual = output / name
            if name == 'run_receipt.json':
                a = json.loads((original / name).read_text())
                b = json.loads(actual.read_text())
                different = [k for k in set(a) | set(b) if k != 'seconds' and a.get(k) != b.get(k)]
                passed = not different
                checks.append({'file': name, 'pass': passed, 'ignored_runtime_field': 'seconds',
                               'different_fields': different, 'replayed_sha256': sha(actual)})
            else:
                digest = sha(actual) if actual.is_file() else None
                checks.append({'file': name, 'pass': digest == item['sha256'],
                               'original_sha256': item['sha256'], 'replayed_sha256': digest})
    receipt = {'status': 'FULL_NATIONAL_REPLAY_EXACT' if result.returncode == 0 and len(checks)==len(spec['files']) and all(c['pass'] for c in checks) else 'REPAIR_REQUIRED',
               'process_exit_code': result.returncode, 'seconds': round(time.monotonic() - start, 3),
               'n_checks': len(checks), 'n_failed': sum(not c['pass'] for c in checks), 'checks': checks,
               'protocol_sha256': sha(report / 'full_replay_protocol.json'), 'log_sha256': sha(report / 'full_replay.log'),
               'same_model_scope_no_external_validation_claim': True}
    (report / 'full_replay_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'checks'}, indent=2))
    return 0 if receipt['status'] == 'FULL_NATIONAL_REPLAY_EXACT' else 1

if __name__ == '__main__':
    raise SystemExit(main())
