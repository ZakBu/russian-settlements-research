#!/usr/bin/env python3
"""Reproduce the selected Word-Ci main model with explicit input/output defaults."""
from pathlib import Path
import argparse,subprocess,sys
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['prepare','full'],default='full');parser.add_argument('--output',type=Path,default=HERE/'output_word_ci_2021_baseline');args=parser.parse_args()
 subprocess.run([sys.executable,str(HERE/'run_word_model.py'),'--inputs',str(HERE/'model_inputs_word_ci_2021.json'),'--output',str(args.output),'--stage',args.stage],check=True)
 subprocess.run([sys.executable,str(HERE/'write_output_manifest.py'),'--directory',str(args.output)],check=True) if args.stage=='full' else None

 if args.stage=='full':
  canonical=HERE.parent/'typology'/'canonical'/args.output.name
  subprocess.run([sys.executable,str(HERE/'apply_literal_typology.py'),'--inputs',str(HERE/'model_inputs_word_ci_2021.json'),'--model-output',str(args.output),'--output',str(canonical)],check=True)
