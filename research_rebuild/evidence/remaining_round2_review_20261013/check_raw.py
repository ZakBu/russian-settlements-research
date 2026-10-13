import hashlib, json, re
from pathlib import Path
import xlrd
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
books, hashes, checks = {}, {}, []

def check(path, sha, sheet, rows, case, prefix=False):
    path = str(path)
    if path not in hashes:
        hashes[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        books[path] = xlrd.open_workbook(path)
    assert hashes[path] == sha, (path, 'hash mismatch')
    sh = books[path].sheet_by_name(str(sheet))
    for row, expected in rows:
        actual = sh.row_values(int(row)-1)
        if prefix: actual = actual[:len(expected)]
        assert actual == expected, (case, row, actual, expected)
    checks.append(dict(case=case, path=path, sha256=sha, sheet=sheet, column_scope='packet explicit prefix' if prefix else 'full sheet row', checked_physical_rows=[r for r,_ in rows]))

v = BASE/'remaining_alias_volga_round2_20261013'
for w in json.loads((v/'native_leaf_context.json').read_text()):
    _,sheet,row=w['uid'].rsplit(':',2)
    check(w['source_path'],w['source_sha256'],sheet,[(r['row_1based'],r['cells']) for r in w['rows']],w['uid'])
for w in json.loads((v/'native2002_county_context.json').read_text()):
    _,sheet,row=w['uid'].rsplit(':',2)
    check(w['source_path'],w['source_sha256'],sheet,[(r['row_1based'],r['cells']) for r in w['county_heading']],w['uid']+' county')
s=BASE/'remaining_alias_south_round2_20261013'
for item in json.loads((s/'alias_native_witnesses.json').read_text()):
    for w in item['native_witnesses']:
        _,sheet,row=w['id'].rsplit(':',2)
        if w['raw'].endswith('.xls'):
            check(w['raw'],w['sha256'],sheet,[(r['row_1based'],r['cells']) for r in w['context']],w['id'])
e=BASE/'remaining_alias_eastnorth_round2_20261013'
for item in json.loads((e/'identity_witnesses.json').read_text()):
    for w in item['raw_witnesses']:
        if w and w['source_file'].endswith('.xls'):
            sheet=w['sheet']
            if str(sheet)=='0':sheet=xlrd.open_workbook(w['source_file']).sheet_names()[0]
            check(w['source_file'],w['source_sha256'],sheet,[(r['row_1based'],r['cells']) for r in w['nearby_raw_rows']],item['case'],prefix=True)
c=BASE/'remaining_alias_center_round2_20261013'
for w in pd.read_csv(c/'source_witnesses.csv.gz').to_dict('records'):
    if isinstance(w['raw_file'],str) and w['raw_file'].endswith('.xls'):
        _,sheet,row=w['source_record_id'].rsplit(':',2)
        check(w['raw_file'],w['raw_sha256'],sheet,[(r['physical_row'],r['cells']) for r in json.loads(w['raw_context_json'])],w['case'])
(OUT/'raw_checks.json').write_text(json.dumps(dict(status='pass',unique_raw_files=len(hashes),row_checks=sum(len(c['checked_physical_rows']) for c in checks),checks=checks),ensure_ascii=False,indent=2)+'\n')
print('PASS',len(hashes),'raw files;',sum(len(c['checked_physical_rows']) for c in checks),'physical rows')
