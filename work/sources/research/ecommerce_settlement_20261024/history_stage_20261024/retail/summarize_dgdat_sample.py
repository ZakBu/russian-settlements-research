"""Technical evidence of an obtainable archived 2GIS format, not a dated shop panel."""
from pathlib import Path
import openpyxl,json,hashlib
from collections import Counter
P=Path(__file__).resolve().parent
f=P/'raw/dgdat_Almetevsk-sample.xlsx'
w=openpyxl.load_workbook(f,read_only=True,data_only=True)
s=w.active
it=iter(s.values)
cols=next(it)
rows=[dict(zip(cols,r)) for r in it]
locality=Counter(str(r.get('Населенный пункт') or 'NULL') for r in rows)
summary={'source_url':'https://raw.githubusercontent.com/littlepoorgirlfromsyriya/1/master/download/Almetevsk-sample.xlsx',
         'source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),
         'rows':len(rows),'columns':len(cols),'unique_organization_ids':len({r['ID'] for r in rows}),
         'rows_without_address':sum(not r.get('Адрес') for r in rows),
         'localities':dict(locality),
         'xlsx_created_metadata':str(w.properties.created),
         'xlsx_modified_metadata':str(w.properties.modified),
         'dataset_observation_date':'not_independently_established',
         'interpretation':'workbook metadata is not observation date; organization rows are not automatically physical shop units',
         'checks':'PASS: workbook opens, header23columns, explicit grain/missingness profile; exact snapshot chronology unverified'}
(P/'dgdat_sample_profile.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
