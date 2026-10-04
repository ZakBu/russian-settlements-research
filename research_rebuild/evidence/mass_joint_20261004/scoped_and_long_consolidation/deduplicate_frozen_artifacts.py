from pathlib import Path
import hashlib, json, os
from collections import defaultdict

roots=[Path('/workspace/settlements-work/continuation_20261003'),Path('/workspace/settlements-delivery'),Path('/workspace/settlements-work/table_builder_probe'),Path('/workspace/settlements-work/continuation_20261004/R4/final_long_preparation')]
groups=defaultdict(list)
for root in roots:
    for p in root.rglob('*'):
        if p.is_file() and not p.is_symlink() and p.stat().st_size>=10_000_000:
            groups[p.stat().st_size].append(p)
replaced=[]
for size,paths in groups.items():
    if len(paths)<2: continue
    byhash={}
    for p in paths:
        with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest not in byhash:
            byhash[digest]=p;continue
        original=byhash[digest]
        a,b=original.stat(),p.stat()
        if (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino) or a.st_mode!=b.st_mode:continue
        # Only byte-identical, finalized artifacts. Paths and all bytes survive.
        tmp=p.with_name(p.name+'.dedup_link_tmp')
        if tmp.exists():raise RuntimeError(str(tmp))
        os.link(original,tmp);os.replace(tmp,p)
        replaced.append({'path':str(p),'canonical_identical_path':str(original),'sha256':digest,'bytes':size,'prior_link_count':b.st_nlink})
receipt={'operation':'hardlink_byte_identical_finalized_artifacts','paths_preserved':True,'content_preserved':True,'replacements':replaced,'estimated_released_bytes':sum(x['bytes'] for x in replaced if x['prior_link_count']==1)}
out=Path('/workspace/settlements-work/continuation_20261004/root/frozen_artifact_deduplication_receipt.json')
out.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'replacements':len(replaced),'estimated_released_bytes':receipt['estimated_released_bytes']}))
