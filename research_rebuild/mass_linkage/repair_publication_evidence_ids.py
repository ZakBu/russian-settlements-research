"""Repair only null nested IDs for a hash-bound accepted publication batch.

The original application remains immutable. The new evidence layer changes no
population, grain, point, identity or other evidence value.
"""
import argparse
import json
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from .coverage import sha


def repair(source, review_path, acceptance_path, output):
    if output.exists():
        raise FileExistsError('New immutable correction directory required')
    review=json.loads(review_path.read_text())
    acceptance=json.loads(acceptance_path.read_text())
    if review.get('verdict')!='APPROVE_BOUNDED_PRIMARY_PUBLICATION_REPLACEMENTS':
        raise ValueError('An independently accepted exact publication batch is required')
    if acceptance['inputs']['review']['sha256']!=sha(review_path):
        raise ValueError('Accepted application review differs')
    if acceptance['outputs']['source_evidence.parquet']['sha256']!=sha(source):
        raise ValueError('Accepted application evidence input differs')
    targets=review['approved_replacement_source_record_ids']
    if not targets or len(targets)!=len(set(targets)):
        raise ValueError('Unique explicit target set required')
    target_set=set(targets);seen=set();changed=[];rows=0
    original=pq.ParquetFile(source)
    output.mkdir(parents=True)
    destination=output/'source_evidence.parquet'
    with pq.ParquetWriter(destination,original.schema_arrow,compression='snappy') as writer:
        for batch in original.iter_batches(batch_size=10000):
            ids=batch.column(batch.schema.get_field_index('source_record_id')).to_pylist()
            if len(set(ids))!=len(ids) or seen.intersection(ids):
                raise ValueError('Evidence IDs collide')
            seen.update(ids);rows+=len(ids)
            column=batch.schema.get_field_index('source_evidence_json')
            payloads=batch.column(column).to_pylist()
            for index,sid in enumerate(ids):
                if sid not in target_set:
                    continue
                value=json.loads(payloads[index])
                if value.get('source_record_id') is not None:
                    raise ValueError('Correction requires a null nested ID, not a conflicting identifier')
                value['source_record_id']=sid
                payloads[index]=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                changed.append(sid)
            table=pa.Table.from_batches([batch])
            table=table.set_column(column,table.schema.field(column),pa.array(payloads,type=table.schema.field(column).type))
            writer.write_table(table)
    if len(changed)!=len(targets) or set(changed)!=target_set:
        raise ValueError('Changed nested IDs differ from the exact approved target set')
    receipt={'status':'metadata_correction_pending_independent_check',
             'scope':'Only null nested source_record_id to the already accepted top-level publication ID',
             'input':{'path':str(source),'sha256':sha(source)},
             'approved_review':{'path':str(review_path),'sha256':sha(review_path)},
             'accepted_application':{'path':str(acceptance_path),'sha256':sha(acceptance_path)},
             'builder_sha256':sha(Path(__file__)),'rows':rows,'changed_rows':len(changed),
             'changed_source_record_ids':sorted(changed),
             'output':{'path':str(destination),'sha256':sha(destination)},
             'other_json_values_changed':False,'new_scientific_admissions':False}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['source','review','acceptance','output']:
        parser.add_argument('--'+name,required=True,type=Path)
    a=parser.parse_args()
    result=repair(a.source,a.review,a.acceptance,a.output)
    print(json.dumps({k:result[k] for k in ['status','rows','changed_rows','output']}))
