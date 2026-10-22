#!/usr/bin/env python3
"""Rebuild frozen feature axes and evaluate fixed specifications in a new directory.
Run from any directory. Primary data are never written. No external services needed.
"""
import argparse,subprocess,sys,json,hashlib
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--skip-features',action='store_true');args=ap.parse_args()
    package=Path(__file__).resolve().parents[1];repo=package.parents[1];work=package/'work'
    raw=repo/'publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz'
    federal=repo/'publication/stage71/accepted_common_federal_territory_axis.csv'
    lock=package/'protocols/final_lock.json';cfg=json.loads(lock.read_text())
    assert hashlib.sha256(raw.read_bytes()).hexdigest()==cfg['input_sha256']
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    def run(parts):
        command=[sys.executable]+[str(p) for p in parts]
        print('RUN',command,flush=True);subprocess.run(command,check=True)
    if not args.skip_features:
        run([work/'geo/build_features_v1.py','--input',raw,'--federal',federal,'--output',out/'geo'])
        run([work/'geo/build_features.py','--input',raw,'--federal',federal,'--output',out/'geo/original2010','--population-axis','original_fallback'])
        run([work/'geo/build_features_atomic.py','--input',raw,'--federal',federal,'--output',out/'geo/exclude_drift_recovery','--exclude-neighbor-uids',package/'agents/D/evidence/point_drift_over5km.csv'])
    run([work/'final_runner.py','--features',out/'geo/features.csv.gz','--raw',raw,'--lock',lock,
         '--original-features',out/'geo/original2010/features.csv.gz','--drift-features',out/'geo/exclude_drift_recovery/features.csv.gz',
         '--output',out/'final','--refits',20])

if __name__=='__main__':main()
