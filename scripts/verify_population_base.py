#!/usr/bin/env python3
"""Read the downloaded census foundation and independently recompute its controls."""
import argparse
import json
from pathlib import Path
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as csv
import pyarrow.parquet as pq


def verify(root):
    directory=root/'data/population'
    metadata=json.loads((directory/'dataset.json').read_text())
    columns=['source_record_id','root','census_year','population','effective_population',
             'working_credit_present','accepted_point_present','finite_ordinary_full3_all_ownpoints']
    long=pq.read_table(directory/'settlements_census_long.parquet',columns=columns)
    assert long.num_rows==metadata['native_observations']==465929
    assert long['source_record_id'].null_count==0
    assert pc.count_distinct(long['source_record_id']).as_py()==long.num_rows
    assert long.group_by(['root','census_year']).aggregate([('source_record_id','count')]).num_rows==long.num_rows
    assert pc.sum(pc.cast(long['working_credit_present'],pa.int64())).as_py()==metadata['credited_native_observations']==431948
    assert pc.sum(pc.cast(long['accepted_point_present'],pa.int64())).as_py()==metadata['accepted_own_points']==447373
    assert pc.sum(pc.cast(long['finite_ordinary_full3_all_ownpoints'],pa.int64())).as_py()==3*metadata['ordinary_full3']
    federal=csv.read_csv(directory/'federal_territories.csv')
    assert federal.num_rows==6
    source_ids=set(long.filter(long['working_credit_present'])['source_record_id'].to_pylist())
    assert not source_ids.intersection(federal['population_source_record_id'].to_pylist())
    coverage=[]
    for row in metadata['coverage']:
        year=row['census_year']
        native=long.filter(pc.and_(pc.equal(long['census_year'],year),long['working_credit_present']))
        fed=federal.filter(pc.equal(federal['census_year'],year))
        assert native['effective_population'].null_count==0
        total=pc.sum(native['effective_population']).as_py()+pc.sum(fed['territory_population']).as_py()
        assert total==row['credited_population']
        coverage.append({'census_year':year,'credited_population':int(total),
                         'denominator':row['denominator'],'coverage_percent':100*total/row['denominator'],
                         'remaining_to_100':row['denominator']-int(total)})
    reads=[]
    for name,count in [('settlements_census_wide.parquet',173242),('ordinary_full3.parquet',142765)]:
        wide=pq.read_table(directory/name)
        assert wide.num_rows==count and pc.count_distinct(wide['root']).as_py()==count
        if name=='ordinary_full3.parquet':assert pc.all(wide['ordinary_full3']).as_py()
        reads.append({'path':'data/population/'+name,'rows':wide.num_rows,'columns':wide.num_columns})
    return {'status':'PASS','scope':'Downloaded census foundation controls; not source-by-source identity accuracy or SGRT validation.',
            'native_records':long.num_rows,'accepted_own_points':metadata['accepted_own_points'],
            'raw_population_nulls_preserved':long['population'].null_count,'coverage_recomputed':coverage,
            'actual_table_reads':[{'path':'data/population/settlements_census_long.parquet','rows':long.num_rows,'columns_read':columns},*reads]}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('.'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=verify(args.root)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    print(text,end='')
