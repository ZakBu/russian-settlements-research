#!/usr/bin/env python3
"""Bounded Arrow normalization: positive NP responses, explicit dense-cell references."""
import argparse,csv,hashlib,json,time,collections
from pathlib import Path
import numpy as np,pyarrow as pa,pyarrow.compute as pc,pyarrow.parquet as pq
E=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--wide-root',default='/workspace/scratch/tochno-np-attach-20261013');p.add_argument('--scratch',default='/workspace/scratch/np-demographic-structure-20261013');p.add_argument('--attachment-receipt',default=str(E.parent/'tochno_np_attach_20261013/receipt.json'));a=p.parse_args();S=Path(a.scratch);S.mkdir(parents=True,exist_ok=True)
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
manifest=json.load(open(a.attachment_receipt));outputs=[];profiles=[];inventory={};start=time.time()
schema=pa.schema([('source_record_id',pa.string()),('root',pa.string()),('observation_year',pa.int16()),('object_scope',pa.string()),('structure_kind',pa.string()),('source_field',pa.string()),('source_value_numeric',pa.float64()),('usable_value',pa.float64()),('value_status',pa.string()),('unit',pa.string()),('source_dataset_version',pa.string()),('canonical_2021_version',pa.bool_()),('original_source_sha256',pa.string()),('original_source_row_1based',pa.float64()),('municipality_allocation',pa.bool_()),('categories_additive',pa.bool_())])
for version,date,rawfile in [('frozen','v20251217','data_allsettlements_anon_156_v20251217.parquet'),('latest','v20260925','data_allsettlements_anon_156_v20260925.parquet')]:
 path=Path(a.wide_root)/('native_np_'+version+'_all_attributes.parquet');f=pq.ParquetFile(path);prefix='tochno_'+version+'__';fields=[x for x in f.schema.names if x.startswith(prefix)];cats=fields[fields.index(prefix+'Указавшие национальную принадлежность'):];rowcol='frozen_row_1based' if version=='frozen' else 'latest_row_1based';original=next((k,v) for k,v in manifest['inputs'].items() if k.endswith(rawfile));stats=collections.Counter();out=S/('np_structure_'+version+'_positive.parquet');writer=pq.ParquetWriter(out,schema,compression='zstd',use_dictionary=True);nrows=npcount=blocked=0
 inventory[version]=dict(all_source_fields=fields,structure_fields=cats,sex_fields=[],age_fields=[],household_fields=[],source_path=str(path),source_sha256=sha(path),original_source_path=original[0],original_source_sha256=original[1],source_version=date,canonical=version=='frozen')
 for batch in f.iter_batches(batch_size=4096,columns=['source_record_id','root',rowcol,prefix+'object_level']+cats):
  b=pa.Table.from_batches([batch]);mask=pc.equal(b[prefix+'object_level'],'Населенный пункт');blocked+=len(b)-pc.sum(pc.cast(mask,pa.int64())).as_py();b=b.filter(mask);npcount+=len(b);ids=b['source_record_id'];roots=b['root'];rows=b[rowcol]
  for col in cats:
   arr=b[col].combine_chunks();valid=arr.is_valid().to_numpy(zero_copy_only=False);v=arr.to_numpy(zero_copy_only=False);finite=valid&np.isfinite(v);published=finite&(v>=0)&(v==np.trunc(v));positive=published&(v>0)
   for status,sel in [('unknown',~valid),('nonfinite',valid&~np.isfinite(v)),('suppressed_minus9',finite&(v==-9)),('invalid_negative',finite&(v<0)&(v!=-9)),('invalid_noninteger_count',finite&(v>=0)&(v!=np.trunc(v))),('published_zero',published&(v==0)),('published_positive',positive)]:stats[col,status]+=int(sel.sum())
   ix=pa.array(np.flatnonzero(positive),type=pa.int64());n=len(ix)
   if not n:continue
   val=pa.array(v[positive]);const=lambda x:pa.array([x]*n)
   table=pa.Table.from_arrays([pc.take(ids,ix),pc.take(roots,ix),const(2021),const('NP'),const('national_response_structure'),const(col[len(prefix):]),val,val,const('published_positive'),const('Человек'),const(date),const(version=='frozen'),const(original[1]),pc.cast(pc.take(rows,ix),pa.float64()),const(False),const(False)],schema=schema);writer.write_table(table,row_group_size=100000);nrows+=n
 writer.close();assert sum(stats.values())==npcount*len(cats)
 for (field,status),n in sorted(stats.items()):profiles.append([date,field[len(prefix):],status,n])
 outputs.append(dict(version=date,canonical=version=='frozen',linked_rows=f.metadata.num_rows,eligible_np_rows=npcount,scope_blocked_rows=blocked,source_fields=len(cats),cells=npcount*len(cats),positive_claims=nrows,path=str(out),sha256=sha(out),status_counts=dict(collections.Counter({s:sum(n for (f,s2),n in stats.items() if s2==s) for s in {s for f,s in stats}}))));print(outputs[-1],flush=True)
with open(E/'field_profile.csv','w') as file:w=csv.writer(file);w.writerow(['source_version','source_field','value_status','cells']);w.writerows(profiles)
json.dump(inventory,open(E/'schema_inventory.json','w'),ensure_ascii=False,indent=2);json.dump(dict(outputs=outputs,observation_year=2021,sex_age_household_fields_absent=True,no_municipality_allocation=True,omission_policy='Only published positive counts materialized; published zero, unknown, suppression and invalid states remain explicitly in immutable wide attachments and field profiles. Missing sparse claim NEVER implies zero.',unit_qualification='Человек; множественные ответы о национальности возможны. Категории и версии не складываются.',elapsed_seconds=time.time()-start),open(E/'receipt.json','w'),ensure_ascii=False,indent=2)
