"""Public POI records showing why a name token cannot establish pickup service."""
from pathlib import Path
import hashlib,json,re,struct
import pyarrow.parquet as pq,pandas as pd
R=Path(__file__).resolve().parent;P=R.parent/'places';pattern=re.compile(r'\bozon\b|\bозон\b',re.I)
rows=[];files=[];examined=0
for path in sorted((P/'selected').glob('overture_ru_selected_*.parquet')):
    examined+=pq.ParquetFile(path).metadata.num_rows
    for batch in pq.ParquetFile(path).iter_batches(batch_size=20000,columns=['id','names','taxonomy','basic_category','geometry','version']):
        for uid,names,tax,basic,geom,version in batch.to_pandas().itertuples(index=False,name=None):
            name=(names or {}).get('primary','');category=(tax or {}).get('primary')
            if not pattern.search(name or ''):continue
            if category not in ['health_care','hospital','medical_center','medical_clinic','gym','dance_club']:continue
            endian='<' if geom[0]==1 else '>';kind=struct.unpack(endian+'I',geom[1:5])[0];offset=9 if kind&0x20000000 else 5
            longitude,latitude=struct.unpack(endian+'dd',geom[offset:offset+16])
            rows.append({'source_place_id':uid,'primary_name':name,'category':category,'basic_category':basic,'longitude':longitude,'latitude':latitude,'source_version':version,'source_release':'2026-09-23.1','source_part':path.name,'source_part_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'name_signal_ozon':True,'counterexample_scope':'Ozon_token_with_non_delivery_source_taxonomy_does_not_identify_PVZ','actual_site_or_affiliation_independently_verified':False})
    files.append(path.name)
    if len(rows)>=10:break
pd.DataFrame(rows).to_csv(R/'name_signal_counterexamples.csv',index=False)
(R/'NAME_SIGNAL_COUNTEREXAMPLES_AUDIT.json').write_text(json.dumps({'status':'PASS' if rows else 'FAIL','examples':len(rows),'purpose':'existence_counterexamples_not_brand_false_positive_rate','examined_selected_rows':examined,'examined_files':files,'full_national_release_exhaustively_examined':False,'all_examples_positive_exact_same_regex':all(pattern.search(x['primary_name']) for x in rows),'all_non_delivery_source_taxonomy':True,'source_objects_public_business_POI_only':True,'no_claim_all_brand_mentions_false':True,'producer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n')
assert rows;print(len(rows),'public counterexamples saved')
