"""Actual repeat execution of the independent audit and incremental models."""
from pathlib import Path
import hashlib,json,subprocess,sys
O=Path(__file__).resolve().parent
files=['independent_validation.json','spatial_block_results.json','independent_point_covariates.parquet','independent_zone_covariates.parquet','functional_incremental_validation.json','functional_spatial_OOF_predictions.csv.gz','functional_same_cohort.parquet']
def pins():return {name:hashlib.sha256((O/name).read_bytes()).hexdigest() for name in files}
before=pins()
for script,log in [('independent_core.py','core_reproduction.log'),('incremental_models.py','functional_reproduction.log')]:
 with (O/log).open('w') as f:subprocess.run([sys.executable,str(O/script)],stdout=f,stderr=subprocess.STDOUT,check=True)
after=pins();checks=[{'file':name,'sha256_before':before[name],'sha256_after':after[name],'byte_identical':before[name]==after[name]} for name in files];result={'actual_full_repeat_execution':True,'checks':checks,'all_byte_identical':all(c['byte_identical'] for c in checks)};(O/'reproduction.json').write_text(json.dumps(result,indent=2));assert result['all_byte_identical'];print(json.dumps({'actual_full_repeat_execution':True,'files_byte_identical':len(checks)}))
