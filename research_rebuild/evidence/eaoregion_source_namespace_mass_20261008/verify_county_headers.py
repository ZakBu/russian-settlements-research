"""Reopen all exact source county headers; independent of State matching."""
import json
from pathlib import Path
import pandas as pd
import xlrd
import build

OUT=Path(__file__).resolve().parent
def main():
    rows=pd.read_csv(OUT/'actual98_native_raw_source_checks.csv',keep_default_na=False)
    sheet=xlrd.open_workbook(rows.iloc[0].source_file).sheet_by_name('Sheet1')
    result=[]
    for row in rows.itertuples():
        rn=int(float(row.raw_locator.rsplit('=',1)[1]))
        headers=[(i+1,sheet.cell_value(i,0)) for i in range(rn-1)
                 if 'район - все сельское население' in str(sheet.cell_value(i,0)).lower()]
        assert headers,row.source_record_id
        header_row,text=headers[-1]
        key=build.county_key(text.split(' - ')[0])
        assert key==build.county_key(row.county_raw),(text,row.county_raw)
        result.append(dict(source_record_id=row.source_record_id,literal_county_header=text,
            literal_county_header_locator=f'Sheet1!row_1based={header_row}',imported_native_county=row.county_raw,
            county_key=key,exact_literal_county_header_checked=True))
    output=OUT/'actual98_literal_county_header_checks.csv'
    pd.DataFrame(result).to_csv(output,index=False)
    verification=dict(status='passed',exact_literal_source_county_headers_verified=len(result),
        source_file=rows.iloc[0].source_file,source_sha256=build.sha(Path(rows.iloc[0].source_file)),
        output_sha256=build.sha(output),code_sha256=build.sha(Path(__file__)))
    (OUT/'county_header_verification_receipt.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(verification,ensure_ascii=False))

if __name__=='__main__':main()
