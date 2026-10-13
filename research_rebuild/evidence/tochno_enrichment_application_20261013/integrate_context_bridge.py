"""Integrate checked context deltas into a NEW bridge, never rewriting frozen inputs."""
from pathlib import Path
import csv,gzip,json,hashlib,shutil,collections
H=Path(__file__).resolve().parent;E=H.parent
BASE=Path('/workspace/scratch/tochno-np-attach-20261013/native_np_municipality_bridge.csv.gz')
PACK=Path('/workspace/scratch/tochno-enrichment-20261013/package')
EXACT=E/'tochno_context_code_resolution_20261013/accepted_context_delta.csv'
GROUP=E/'tochno_context_code_groups_20261013/accepted_code_context_delta.csv'
CLAIMS=E/'tochno_context_code_groups_20261013/all_source_claim_rows.csv'
OUT=H/'native_np_municipality_bridge.csv.gz'
def load(p):
 with p.open(newline='') as f:return list(csv.DictReader(f))
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
exact={(r['source_record_id'],r['municipality_role']):r for r in load(EXACT)}
groups={(r['source_record_id'],r['municipality_role']):r for r in load(GROUP)}
claims=collections.defaultdict(list)
for r in load(CLAIMS):claims[(r['source_record_id'],r['municipality_role'])].append(r)
assert len(exact)==4 and len(groups)==78 and not exact.keys()&groups.keys()
counts=collections.Counter();seen=collections.Counter();source_pin=sha(BASE)
extra=['prior_context_status','context_resolution_rule','municipality_source_row_ambiguous','municipality_raw_attribute_row_selected','boundary_comparability_asserted','source_claim_rows','all_municipality_source_row1_claims','all_municipality_oktmo_raw_claims','country_raw','code_namespace']
with gzip.open(BASE,'rt',newline='') as src,gzip.open(OUT,'wt',newline='',compresslevel=1) as dst:
 reader=csv.DictReader(src);fields=list(reader.fieldnames)+extra;writer=csv.DictWriter(dst,fields);writer.writeheader()
 for r in reader:
  k=(r['source_record_id'],r['municipality_role']);prior=r['context_status'];row=r['municipality_frozen_row_1based'];selected=bool(row)
  r.update(prior_context_status=prior,context_resolution_rule='frozen_source_context_rule',municipality_source_row_ambiguous=str(prior=='ambiguous_source_context'),municipality_raw_attribute_row_selected=str(selected),boundary_comparability_asserted='False',source_claim_rows='1' if selected else '0',all_municipality_source_row1_claims=json.dumps([int(float(row))] if row else []),all_municipality_oktmo_raw_claims=json.dumps([r['municipality_oktmo_raw']] if selected else [],ensure_ascii=False),country_raw='Российская Федерация',code_namespace='RU_OKTMO')
  if k in exact:
   d=exact[k];seen['exact']+=1
   for col in ['municipality_frozen_row_1based','municipality_object_level','municipality_label_raw','municipality_oktmo_raw','municipality_oktmo_code8']:
    r[col]=d[col]
   r.update(context_status='exact_unique_source_context',context_resolution_rule=d['code_basis'],municipality_source_row_ambiguous='False',municipality_raw_attribute_row_selected='True',source_claim_rows='1',all_municipality_source_row1_claims=json.dumps([int(d['municipality_frozen_row_1based'])]),all_municipality_oktmo_raw_claims=json.dumps([d['municipality_oktmo_raw']]))
  elif k in groups:
   d=groups[k];cs=claims[k];seen['code_group']+=1
   assert len(cs)==int(d['source_claim_rows']) and len(set(x['municipality_oktmo_code8'] for x in cs))==1
   raw_codes=list(dict.fromkeys(x['municipality_oktmo_raw'] for x in cs));levels=list(dict.fromkeys(x['municipality_object_level'] for x in cs));assert len(levels)==1
   r.update(context_status=d['context_status'],context_resolution_rule=d['code_basis'],municipality_frozen_row_1based='',municipality_object_level=levels[0],municipality_oktmo_raw=raw_codes[0] if len(raw_codes)==1 else '',municipality_oktmo_code8=d['municipality_oktmo_code8'],municipality_source_row_ambiguous='True',municipality_raw_attribute_row_selected='False',source_claim_rows=str(len(cs)),all_municipality_source_row1_claims=d['all_municipality_source_row1_claims'],all_municipality_oktmo_raw_claims=json.dumps(raw_codes,ensure_ascii=False))
  counts[(r['municipality_role'],r['context_status'])]+=1;writer.writerow(r)
assert seen=={'exact':4,'code_group':78} and sum(counts.values())==466242
# A package path may be hardlinked to frozen evidence. Never open it for writing.
p=PACK/'links/native_np_municipality_bridge.csv.gz';p.unlink();shutil.copyfile(OUT,p)
receipt={'source_bridge_sha256':source_pin,'new_bridge_path':str(OUT),'package_bridge_path':str(p),'new_bridge_sha256':sha(OUT),'delta_rows_applied':dict(seen),'rows':sum(counts.values()),'status_counts':[{'role':a,'status':b,'rows':n} for (a,b),n in sorted(counts.items())],'new_columns':extra,'source_row_ambiguity_preserved':True,'boundary_comparability_asserted':False,'frozen_inputs_modified':False}
(H/'context_bridge_integration_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
