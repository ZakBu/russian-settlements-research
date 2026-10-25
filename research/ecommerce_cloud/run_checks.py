"""Run existing computational audits, not a causal-identification review."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'work/sources/research/ecommerce_settlement_20261024'
for relative in [
    'execution_20261024/audit/peer_review.py',
    'history_stage_20261024/verify_stage.py',
    'settlement_role_stage_20261024/verify_results.py',
]:
    path = BASE / relative
    print(f'Checking {relative}', flush=True)
    subprocess.run([sys.executable, str(path)], cwd=path.parent, check=True)
print('Computational checks finished. Causal research remains unfinished.')
