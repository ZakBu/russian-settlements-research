"""Pin the independently accepted actual report inventory without changing values."""
from pathlib import Path
import json,argparse,hashlib,importlib.util
R=Path(__file__).resolve().parents[2]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser();a.add_argument('--admission',required=True);a.add_argument('--output',required=True);v=a.parse_args();ad=Path(v.admission);ad=ad if ad.is_absolute()else R/ad;inv=R/'delivery/cycle07_current_primary_v1/report_source_inventory_v1.json';assert sha(inv)in ad.read_text();j=json.loads(ad.read_text());assert j['all_checks_passed']is True
 c=json.loads((R/'delivery/cycle07_current_primary_v1/report_inputs_PENDING_v1.json').read_text());manifest={'path':str(inv.relative_to(R)),'sha256':sha(inv)};ap={'path':str(ad.relative_to(R)),'sha256':sha(ad),'required_values':[[['all_checks_passed'],True]]}
 for role,spec in c['artifacts'].items():
  if role in ['word_text','bibliography']:spec['reference_only']=True;continue
  if role=='analysis_status':continue
  spec['manifest']=manifest
  if role.endswith('_admission')or role.endswith('_numeric_review')or role=='functional_case_receipt':spec.update(independent_review=True,required_values=[[['all_checks_passed'],True]])
  elif role.startswith('map_')or role=='atlas_receipt':spec['computed_draft']=True
  else:spec['admission']=ap
 out=Path(v.output);assert not out.exists();out.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n');sp=importlib.util.spec_from_file_location('actual_report',R/'delivery/cycle07_tools/build_report_v6.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);paths,watch=m.verify(c);print(json.dumps({'all_bound_files_verified':len(paths),'watched_files':len(watch),'config_sha256':sha(out)}))
if __name__=='__main__':main()
