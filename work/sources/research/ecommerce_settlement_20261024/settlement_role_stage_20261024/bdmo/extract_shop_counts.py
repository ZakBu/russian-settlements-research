"""Bounded extraction of physical-object counts from the public BDMO mirror.

Municipal data are not automatically settlement observations. No counts are summed
across municipal levels or overlapping shop categories.
"""
from pathlib import Path
from collections import Counter
import json
import hashlib
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc

OUT=Path(__file__).resolve().parent


def main():
    source=next((OUT/'raw').glob('*.parquet'))
    f=pq.ParquetFile(source)
    cols=['indicator_code','indicator_name','obroz','vidtorgv','region_id','region_name',
          'mun_level','mun_district','municipality','oktmo','mun_type','mun_type_oktmo',
          'oktmo_stable','oktmo_history','oktmo_year_from','oktmo_year_to',
          'year','indicator_value','indicator_unit','indicator_period','comment']
    target=OUT/'shop_object_counts_all_municipal_levels.parquet'
    writer=None
    profiles=Counter()
    rows=0
    nulls=0
    units=set()
    for batch in f.iter_batches(batch_size=131072,columns=cols):
        t=pa.Table.from_batches([batch])
        t=t.filter(pc.equal(t['indicator_code'],'Y48002001'))
        if not len(t):
            continue
        if writer is None:
            writer=pq.ParquetWriter(target,t.schema,compression='zstd')
        writer.write_table(t)
        rows+=len(t)
        nulls+=t['indicator_value'].null_count
        units.update(pc.unique(t['indicator_unit']).to_pylist())
        g=t.group_by(['year','mun_level','indicator_period','obroz']).aggregate([
            ('indicator_code','count'),('indicator_value','count')])
        for r in g.to_pylist():
            key=(r['year'],r['mun_level'],r['indicator_period'],r['obroz'])
            profiles[key]+=r['indicator_code_count']
    if writer:
        writer.close()
    assert rows==3163287
    assert units=={'Единица'}
    import csv
    with (OUT/'count_observation_profiles.csv').open('w',newline='') as out:
        w=csv.writer(out,lineterminator='\n')
        w.writerow(['year','mun_level','indicator_period','obroz','observations'])
        w.writerows([*k,v] for k,v in sorted(profiles.items()))
    summary={
        'source':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'rows':rows,'null_values':nulls,'units':list(units),
        'indicator_code':'Y48002001',
        'definition':'Count of physical retail/catering objects, broken down by obroz. All original categories retained for explicit selection.',
        'grain':'municipality × year × original observation period × object category',
        'municipal_level_is_not_settlement':True,
        'source_website':'https://tochno.st/datasets/bdmo',
        'no_additive_totals_computed':True,
    }
    (OUT/'extraction_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
