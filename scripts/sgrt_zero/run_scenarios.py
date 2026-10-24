#!/usr/bin/env python3
"""Compute the declared daily-service sensitivities, without changing policy."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
try:
 from .hierarchy import file_sha256
except ImportError:
 from hierarchy import file_sha256


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--screens',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--resume-source-and-code-matched',action='store_true',help='Explicitly reuse existing results with the same input and code fingerprints')
 a=p.parse_args();cfg=json.loads((a.screens/'summary.json').read_text());edges=a.screens/'daily_edges.parquet';script=Path(__file__).with_name('hierarchy.py')
 expected_inputs={str(edges):file_sha256(edges),str(a.reference):file_sha256(a.reference)};code_sha=file_sha256(script);records={}
 a.output.mkdir(parents=True,exist_ok=True)
 order=[cfg['main_scenario'],*[k for k in cfg['scenarios'] if k!=cfg['main_scenario']]]
 for sid in order:
  policy=cfg['scenarios'][sid];out=a.output/sid;summary_path=out/'summary.json';old=json.loads(summary_path.read_text()) if summary_path.exists() else {}
  required=[out/(n+'.parquet') for n in ['level0_units','level0_memberships','level0_provider_anchors','daily_edge_evidence']]
  reuse=a.resume_source_and_code_matched and old.get('input_sha256')==expected_inputs and old.get('hierarchy_code_sha256')==code_sha and all(p.is_file() for p in required)
  if not reuse:
   command=[sys.executable,str(script),'--edges',str(edges),'--reference',str(a.reference),'--scenario-id',sid,'--families',*policy['expected_families'],'--core-families',*policy['core_families'],'--output',str(out)]
   print('RUN',' '.join(command),flush=True);subprocess.run(command,check=True)
  summary=json.loads(summary_path.read_text());summary['this_driver_execution']='existing_source_and_code_matched' if reuse else 'newly_computed'
  records[sid]=summary;print(json.dumps({'scenario':sid,'execution':summary['this_driver_execution'],'units':summary['level0_units'],'inhabited_multi_np':summary['inhabited_multi_np_service_areas']}),flush=True)
 result={'main_scenario':cfg['main_scenario'],'scenarios':records,'source_screens_summary_sha256':file_sha256(a.screens/'summary.json'),'hierarchy_code_sha256':code_sha,'results_are_not_counts_of_observed_sgrt':True}
 (a.output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
