"""Replay Stage II using read-only stage71 from a checkout; output outside research artifacts."""
import argparse,subprocess,sys,shutil,json,hashlib
from pathlib import Path

ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,required=True);ap.add_argument('--workdir',type=Path,required=True);ap.add_argument('--geography-only',action='store_true');a=ap.parse_args()
root=Path(__file__).resolve().parents[1];scripts=root/'scripts';work=a.workdir.resolve();work.mkdir(exist_ok=True,parents=True)
raw=a.repo_root.resolve()/'publication/stage71';panel=raw/'ordinary_full3_with_primary_population_sources.csv.gz';fed=raw/'accepted_common_federal_territory_axis.csv'
assert hashlib.sha256(panel.read_bytes()).hexdigest()=='d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c'
commands=[]
def run(args):
 cmd=[sys.executable,*map(str,args)];commands.append(cmd)
 with (work/'commands.json').open('w') as f:json.dump(commands,f,indent=2)
 subprocess.run(cmd,check=True)
run([scripts/'geography/reproduce_geography.py','--input',panel,'--federal',fed,'--workdir',work/'geo'])
for name in ['c2_sensitivity.py','c2_geometry_diagnostic.py']:
 src=scripts/'geography'/name
 if src.exists():
  txt=src.read_text().replace('/workspace/scratch/c21afd18c709/stage2_work/publish/research/geographic_regimes_stage2/protocols/descriptive_claims.md',str(root/'protocols/descriptive_claims.md'))
  (work/'geo'/name).write_text(txt);run([work/'geo'/name])
if not a.geography_only:
 run([root/'validation/audit/audit_stage2.py','--input',panel,'--out',work/'audit'])
 run([scripts/'compare.py','--metrics',work/'geo/outputs/territory_metrics.csv','--output',work/'comparison'])
 run([scripts/'c1_sensitivity.py','--input',panel,'--points',work/'geo/outputs/point_distances.csv.gz','--pairs',work/'comparison/comparison_registry.csv.gz','--output',work/'c1_checks'])
print('Completed. Does not re-fetch external evidence, repair source values, or certify scientific claims.')
