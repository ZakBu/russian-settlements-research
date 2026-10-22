"""Exact monotone access-policy overlay; immutable v1 source geometry remains untouched."""
from pathlib import Path
import json,time,datetime,collections
import pandas as pd,numpy as np,pyarrow as pa,pyarrow.parquet as pq,pyarrow.compute as pc
from graph_io import sha
from road_profile import PERMIT,DENY,UNCERTAIN,access_decision,exclusions
H=Path(__file__).resolve().parent;OLD=H.parent/'cycle06_network2021';T=Path('/tmp/sgrt_network2021_access_v2');OT=Path('/tmp/sgrt_network2021')
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 start=time.monotonic();ad=H.parents[1]/'reviews/cycle06/network2021_access_v2_finite_policy_admission.json';assert ad.exists();proto=json.loads((H/'protocol.json').read_text());assert proto['access_policy_admission_sha256']==sha(ad)
 oldr=json.loads((OLD/'road_extraction_receipt.json').read_text());assert sha(OT/'road_ways.parquet')==oldr['working_geometry_sha256'];assert not (T/'road_ways.parquet').exists()
 outdir=H/'profile_ledger';outdir.mkdir();counts=collections.Counter();categories=collections.Counter();reasoncounts=collections.Counter();parts=[];removed=set();oldpins={};observed=collections.Counter()
 for i,part in enumerate(oldr['profile_ledger_parts']):
  p=OLD/part['path'];assert sha(p)==part['sha256'];oldpins[str(p.relative_to(H.parent))]=part['sha256'];d=pd.read_parquet(p);raw=d.effective_car_access.fillna('');norm=raw.str.strip().str.casefold();cat=norm.map(lambda x:'permit' if x in PERMIT else 'deny' if x in DENY else 'uncertain');observed.update(raw.tolist());rs=d.exclusion_reasons_json.copy()
  for j in d.index[(cat!='permit')|~d.accepted]:
   other=[x for x in json.loads(rs[j]) if not x.startswith('effective_car_access_')];other+=[] if cat[j]=='permit' else ['effective_car_access_'+cat[j]+'_'+norm[j]];rs[j]=json.dumps(other)
  accept=rs.eq('[]');assert not (accept&~d.accepted).any(),'Finite scope must be subset, not expansion';remove=d.accepted&~accept;removed.update(d.loc[remove,'way_id'].tolist());categories.update(cat.tolist());counts['road_source_ways']+=len(d);counts['accepted']+=int(accept.sum());counts['excluded']+=int((~accept).sum())
  for x in rs[~accept]:reasoncounts.update(json.loads(x))
  counts['destination_roads_retained']+=int((accept&norm.eq('destination')).sum())
  for key in [-1,0,1]:counts[f'direction_{key}']+=int((accept&d.static_direction.eq(key)).sum())
  counts['explicit_bidirectional_roundabouts']+=int((accept&d.junction_raw.eq('roundabout')&d.static_direction.eq(0)).sum())
  overlay=pd.DataFrame(dict(way_id=d.way_id,source_ledger_part=part['path'],source_ledger_row_0based=np.arange(len(d),dtype='uint32'),effective_car_access_raw=raw,effective_car_access_normalized=norm,access_category=cat,old_accepted=d.accepted,accepted=accept,exclusion_reasons_json=rs));q=outdir/f'part_{i:03d}.parquet';overlay.to_parquet(q,index=False,compression='zstd');parts.append(dict(path=str(q.relative_to(H)),rows=len(overlay),sha256=sha(q)))
 assert counts['road_source_ways']==5663409 and counts['accepted']==5591746 and len(removed)==158
 census=pd.read_csv(H/'complete_effective_access_literal_census.csv',keep_default_na=False);assert dict(observed)==dict(zip(census.effective_access_literal,census.all_source_ways))
 oldpf=pq.ParquetFile(OT/'road_ways.parquet');writer=pq.ParquetWriter(T/'road_ways.parquet',oldpf.schema_arrow,compression='zstd');witness=[];geometry_kept=0
 for b in oldpf.iter_batches(batch_size=20000):
  table=pa.Table.from_batches([b]);take=pc.is_in(table['way_id'],value_set=pa.array(sorted(removed),type=pa.int64()));dropped=table.filter(take)
  if len(dropped):
   for row in dropped.to_pylist():
    tags=json.loads(row['tags']);raw,norm,category,reason=access_decision(tags);assert category!='permit' and reason in exclusions(tags);row.update(effective_car_access_raw=raw,effective_car_access_normalized=norm,access_category=category,v2_exclusion_reason=reason);witness.append(row)
  retained=table.filter(pc.invert(take));writer.write_table(retained);geometry_kept+=len(retained)
 writer.close();assert geometry_kept==counts['accepted'] and len(witness)==158 and {r['way_id'] for r in witness}==removed
 pd.DataFrame(witness).to_parquet(H/'removed_source_way_witnesses.parquet',index=False);assert collections.Counter(r['access_category'] for r in witness)=={'deny':21,'uncertain':137}
 dump(H/'road_extraction_receipt.json',dict(status='ACTUAL_MONOTONE_SOURCE_ACCESS_V2_GEOMETRY_FILTERED',source_filter_receipt_sha256=sha(H/'source_filter_receipt.json'),profile_code_sha256=sha(H/'road_profile.py'),extract_code_sha256=sha(Path(__file__)),counts=dict(counts),exclusion_reason_counts=dict(reasoncounts),access_category_counts=dict(categories),profile_ledger_parts=parts,profile_ledger_format='source_v1_immutable_metadata_plus_v2_full_decision_overlay',source_metadata_ledger_namespace='../cycle06_network2021',source_metadata_ledger_sha256=oldpins,working_geometry_parquet=str(T/'road_ways.parquet'),working_geometry_sha256=sha(T/'road_ways.parquet'),working_geometry_bytes=(T/'road_ways.parquet').stat().st_size,prior_geometry_sha256=oldr['working_geometry_sha256'],geometry_relation='Exact source-row subset of existing independently audited v1 geometry: only158 ways excluded, no retained source vertices/tags/direction/speed modified.',removed_source_ways=len(removed),added_source_ways=0,all42_literal_census_readback=True,empty_priority_conflict_basis='Independent full accepted raw-tag census found zero explicit-empty highest-priority access keys and zero masking conflicts; frozen policy still quarantines future empty conflicts.',seconds=time.monotonic()-start,limits=oldr['limits']))
 print(json.dumps(dict(counts)),flush=True)
if __name__=='__main__':main()
