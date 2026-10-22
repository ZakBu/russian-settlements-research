"""Portable replay preserving immutable run scripts; stages copied into requested workdir."""
import argparse,subprocess,sys
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--input',required=True,type=Path);ap.add_argument('--federal',required=True,type=Path);ap.add_argument('--workdir',required=True,type=Path);a=ap.parse_args();a.workdir.mkdir(parents=True,exist_ok=True);src=Path(__file__).parent
# Existing immutable scripts contain original cloud path. Materialise exact path substitutions
# as new scripts; each stage records hashes of the script actually executed.
old='/workspace/scratch/c21afd18c709/repo/publication/stage71'
for name in ['geography.py','enrich.py','finalize.py','figures.py','protocol_geography.md']:
 txt=(src/name).read_text()
 if name=='geography.py':txt=txt.replace(old+'/ordinary_full3_with_primary_population_sources.csv.gz',str(a.input.resolve()))
 if name in ['enrich.py','figures.py']:
  txt=txt.replace("Path('"+old+"')",'Path('+repr(str(a.input.resolve().parent))+')')
  txt=txt.replace("R/'ordinary_full3_with_primary_population_sources.csv.gz'",'Path('+repr(str(a.input.resolve()))+')')
  txt=txt.replace("R/'accepted_common_federal_territory_axis.csv'",'Path('+repr(str(a.federal.resolve()))+')')
 (a.workdir/name).write_text(txt)
for name in ['geography.py','enrich.py','finalize.py','figures.py']:subprocess.run([sys.executable,str(a.workdir/name)],check=True)
