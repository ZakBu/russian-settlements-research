#!/usr/bin/env python3
"""Artifact integrity; source-backed maps are distinct from scientific closure."""
from pathlib import Path
import hashlib,json
from PIL import Image
H=Path(__file__).resolve().parent;R=H.parent
m=json.loads((H/'map_manifest.json').read_text());fail=[]
for r in m:
 for p,sha in r['inputs'].items():
  actual=hashlib.sha256((R/p).read_bytes()).hexdigest()
  if actual!=sha:fail.append(f'Changed source: {p}')
 for o in r['outputs']:
  p=H/o['path']
  if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=o['sha256']:fail.append(f'Missing or changed output: {p.name}')
  if p.suffix=='.png':
   with Image.open(p) as im:
    im.verify()
   with Image.open(p) as im:
    if min(im.size)<300:fail.append(f'Too small: {p.name}')
figures=[r['figure'] for r in m];word=[f for f in figures if f.startswith('04_nine_word_types')];hier=[f for f in figures if f.startswith('03_road_hierarchy')]
out={'artifact_integrity_status':'PASS' if not fail else 'FAIL','figure_sets':len(m),'files':sum(len(r['outputs']) for r in m),'failures':fail,'word_type_panels_present':word,'road_hierarchy_figures_present':hier,'model_maps_pending':not bool(word and hier),'scientific_acceptance_implied':False,'semantics':'Integrity validates hashes and images; source coverage and functional mechanism limitations remain explicit in figures and research review.'}
(H/'validation_receipt.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2));raise SystemExit(bool(fail))
