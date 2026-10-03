"""Read the preserved PostgreSQL COPY classifier without losing code widths."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import pandas as pd
import duckdb


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def copy_value(value: str) -> str | None:
    if value == r'\N':
        return None
    escapes = {'b':'\b','f':'\f','n':'\n','r':'\r','t':'\t','v':'\v','\\':'\\'}
    def replace(match):
        token = match.group(1)
        if token.startswith('x'):
            return chr(int(token[1:],16))
        if token[0].isdigit():
            return chr(int(token,8))
        return escapes.get(token,token)
    return re.sub(r'\\(x[0-9a-fA-F]{1,2}|[0-7]{1,3}|.)',replace,value)


def read_copy(path: Path) -> pd.DataFrame:
    rows, active, ended = [], False, False
    for line_no, line in enumerate(path.open(encoding='utf-8'),1):
        if line.strip() == 'COPY okato (code, name_raw, name, status, name_full, is_settlement) FROM stdin;':
            if active or ended:
                raise ValueError('unexpected repeated classifier COPY block')
            active = True
            continue
        if not active:
            continue
        if line.rstrip('\r\n') == r'\.':
            ended, active = True, False
            continue
        values = [copy_value(v) for v in line.rstrip('\r\n').split('\t')]
        if len(values) != 6 or not re.fullmatch(r'\d{8}|\d{11}',values[0] or '') or values[5] not in {'t','f'}:
            raise ValueError(f'unexpected classifier row at line {line_no}')
        rows.append(dict(zip(['historical_okato','name_raw','name','status','name_full','is_settlement_raw'],values),
                         source_line_1based=line_no))
    if not ended:
        raise ValueError('classifier COPY block missing or incomplete')
    return pd.DataFrame(rows)


def main():
    p=argparse.ArgumentParser()
    for k in ['source','database','output']:
        p.add_argument('--'+k,required=True,type=Path)
    a=p.parse_args()
    if a.output.exists():
        raise FileExistsError('use a new immutable output')
    parsed=read_copy(a.source)
    settlements=parsed[parsed.is_settlement_raw.eq('t')].copy()
    with duckdb.connect(str(a.database),read_only=True) as db:
        legacy=db.execute('select historical_okato,name_raw,name,status,name_full,is_settlement_raw from historical_okato_142_2009').df()
    columns=list(legacy.columns)
    # Compare multiplicities as well as raw field values; no first-row dedupe.
    def bag(frame):
        return frame[columns].astype('string').fillna('<NULL>').value_counts(dropna=False).sort_index()
    actual, expected=bag(settlements),bag(legacy)
    matches=actual.equals(expected)
    if not matches:
        diff=actual.subtract(expected,fill_value=0)
        mismatch=int(diff.ne(0).sum())
    else:
        mismatch=0
    a.output.mkdir(parents=True)
    parsed['source_sha256']=sha(a.source)
    parsed['source_snapshot_version']='142/2009'
    parsed['valid_from']=None;parsed['valid_to']=None
    parsed.to_parquet(a.output/'raw_classifier.parquet',index=False)
    receipt={'status':'raw_fields_match_legacy' if matches else 'mismatch_requires_review',
             'source_sha256':sha(a.source),'source_file':str(a.source),'source_snapshot_version':'142/2009',
             'all_rows':len(parsed),'settlement_rows':len(settlements),'legacy_rows':len(legacy),
             'differing_field_value_groups':mismatch,'comparison_columns':columns,
             'outputs':{'raw_classifier.parquet':sha(a.output/'raw_classifier.parquet')},
             'limitations':['Classifier row membership and original code/name/type only; no census identity or legal validity interval admitted.'],
             'builder_sha256':sha(Path(__file__))}
    (a.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':
    main()
