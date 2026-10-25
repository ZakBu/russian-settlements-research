"""Compare independent manual and public full calculations, retaining path/SHA differences explicitly."""
from pathlib import Path
import argparse, json, hashlib
import pandas as pd
p=argparse.ArgumentParser();p.add_argument('--manual',type=Path,required=True);p.add_argument('--public',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();m=a.manual;b=a.public
pairs=[]
for folder in ['hierarchy','upward','upward_extended']:
 for f in sorted((b/folder).rglob('*.parquet')):
  if f.name in {'units.parquet','memberships.parquet','level0_units.parquet','level0_memberships.parquet'}:pairs.append((str(f.relative_to(b)),m/f.relative_to(b),f,'partition'))
for folder in ['routes','routes_wb','routes_yandex']:
 for f in sorted((b/folder/'nearest').glob('*.parquet')):
  mf=m/('routes_final' if folder=='routes' and (m/'routes_final/nearest').is_dir() else folder)/'nearest'/f.name;pairs.append((str(f.relative_to(b)),mf,f,'route'))
def role(*names):return next((m/n for n in names if (m/n).is_dir()),m/names[-1])
health=role('health/public_scope_complete_corrected','health/public_scope_corrected');edu=role('education_general_scope_corrected','education');com=role('commerce_address_components_corrected','commerce_identity_corrected','commerce');clinical=role('federal_medical/functions_complete_scope_corrected','federal_medical/functions')
for role,mroot,broot,names in [('medical',health,b/'health/public_scope_corrected',['np_supply.parquet','physical_sites.parquet','federal_service_evidence_with_identity.parquet']),('education',edu,b/'education',['physical_sites.parquet','np_supply.parquet','source_inventory_current.parquet']),('commerce',com,b/'commerce',['sites.parquet','sites_wb_current.parquet','yandex/sites_yandex_current.parquet','fivepost/sites_5post_current.parquet','fivepost/sites_grocery_current_host_proxy.parquet']),('clinical',clinical,b/'federal_medical/functions',['care_rows_classified.parquet','service_evidence_by_care_address.parquet'])]:
 for name in names:pairs.append((str((broot/name).relative_to(b)),mroot/name,broot/name,role))
rows=[];failed=[]
for label,x,y,role in pairs:
 r={'path':label,'role':role,'manual':str(x),'public':str(y)}
 if not x.is_file() or not y.is_file():r['failure']='missing';rows.append(r);failed.append(label);continue
 sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
 r.update(manual_sha256=sha(x),public_sha256=sha(y))
 if r['manual_sha256']==r['public_sha256']:
  import pyarrow.parquet as pq
  count=pq.ParquetFile(x).metadata.num_rows;r.update(manual_rows=count,public_rows=count,all_scientific_values_equal_exactly=True,byte_identical_fastpath=True,dtype_differences={},explicit_provenance_column_differences={});rows.append(r);print(label,True,flush=True);continue
 u=pd.read_parquet(x);v=pd.read_parquet(y);r['manual_rows']=len(u);r['public_rows']=len(v)
 r['dtype_differences']={k:{'manual':str(u[k].dtype),'public':str(v[k].dtype)} for k in set(u.columns)&set(v.columns) if str(u[k].dtype)!=str(v[k].dtype)}
 pathcols=['provider_source_input','source_supply_sha256'] if role=='route' else []
 r['explicit_provenance_column_differences']={}
 for col in pathcols:
  if col in u and col in v and not u[col].equals(v[col]):r['explicit_provenance_column_differences'][col]={'manual_distinct':u[col].drop_duplicates().astype(str).tolist(),'public_distinct':v[col].drop_duplicates().astype(str).tolist()}
 u=u.drop(columns=pathcols,errors='ignore');v=v.drop(columns=pathcols,errors='ignore')
 keys=next(([k] for k in ['origin_id','unit_id','source_record_id','provider_id'] if k in u and k in v and u[k].is_unique and v[k].is_unique),None)
 if keys:u=u.sort_values(keys).reset_index(drop=True);v=v.sort_values(keys).reset_index(drop=True)
 try:pd.testing.assert_frame_equal(u,v,check_dtype=False,check_exact=True);r['all_scientific_values_equal_exactly']=True
 except AssertionError as e:r['all_scientific_values_equal_exactly']=False;r['failure']=str(e)[:2000];failed.append(label)
 rows.append(r);print(label,not bool(r.get('failure')),flush=True)
assert sum(x[3]=='partition' for x in pairs)==30, 'Expected fifteen complete partition pairs'
assert sum(x[3]=='route' for x in pairs)==23, 'Expected all twenty-three route classes'
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps({'manual_root':str(m),'public_root':str(b),'tables':rows,'table_count':len(rows),'failures':failed,'provenance_policy':'Only two explicitly recorded route provenance columns are separated; all source/provider/cost/support/clinical/scientific columns compared exactly.'},ensure_ascii=False,indent=2)+'\n');raise SystemExit(bool(failed))
