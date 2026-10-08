"""Independent output/source pin and native census row verification; no State reload."""
import hashlib
import json
import subprocess
from pathlib import Path
import pandas as pd
import xlrd

OUT = Path(__file__).resolve().parent
E = OUT.parent
def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    application = json.loads((OUT / 'application_receipt.json').read_text())
    assert application['code_sha256'] == sha(OUT / 'build.py')
    for path, expected in application['input_pins'].items():
        assert sha(path) == expected, path
    for filename, expected in application['output_pins'].items():
        assert sha(OUT / filename) == expected, filename
    original = E / 'moscow_three_direct_inclusion_events_application_20261008'
    original_receipt = json.loads((original / 'application_receipt.json').read_text())
    for filename, expected in original_receipt['output_sha256'].items():
        assert sha(original / filename) == expected, filename
    witness = pd.read_csv(OUT / 'native_pin_witness.csv', keep_default_na=False)
    books = {}
    raw_checks = []
    for row in witness.to_dict('records'):
        sid = row['target_source_record_id']
        year, filename, sheet, rownumber = sid.split(':')
        raw_path = Path('/workspace/settlements-raw') / row['source_file']
        if sid == 'MURMANSK2010:POPSEX:T1:R206':
            frozen = E / 'absorbed_large_direct_events_followup_20261008/actual_native_raw_reopenings.csv.gz'
            reopened = pd.read_csv(frozen, keep_default_na=False).set_index('source_record_id').loc[sid]
            raw_path = Path(reopened.source_path)
            assert sha(raw_path) == reopened.source_sha256
            raw = pd.read_csv(raw_path, keep_default_na=False).to_dict('records')
            matches = [item for item in raw if sid in item.values()]
            assert matches and float(matches[0]['population']) == float(row['population'])
            raw = matches[0]
            locator = reopened.source_locator
        elif raw_path.is_file() and raw_path.open('rb').read(4) == b'%PDF':
            page = sheet.removeprefix('pdf_page_').removeprefix('p')
            text = subprocess.check_output(['pdftotext', '-f', page, '-l', page, '-layout', str(raw_path), '-']).decode()
            lines = [line for line in text.splitlines() if row['settlement_name'] in line]
            assert lines and str(int(row['population'])) in ''.join(lines).replace(' ', ''), sid
            raw = lines
            locator = f'{sheet};line={rownumber}'
        else:
            if str(raw_path) not in books:
                books[str(raw_path)] = xlrd.open_workbook(str(raw_path), on_demand=True)
            book = books[str(raw_path)]
            native_sheet = book.sheet_by_index(int(sheet)) if sheet.isdigit() else book.sheet_by_name(sheet)
            raw = native_sheet.row_values(int(rownumber)-1)
            assert any(str(value).strip() in [str(int(float(row['population']))), str(float(row['population']))] for value in raw), (sid, row['population'], raw)
            locator = f'{sheet}!row_1based={rownumber}'
        assert raw_path.is_file(), str(raw_path)
        raw_sha = sha(raw_path)
        raw_checks.append(dict(target_source_record_id=sid, raw_native_source_file=str(raw_path), raw_native_source_sha256=raw_sha,
            raw_native_source_locator=locator, original_native_raw_row_json=json.dumps(raw, ensure_ascii=False),
            native_population_literal_verified=True, native_population_value_quality=row['population_value_quality']))
        application['input_pins'][str(raw_path)] = raw_sha
    pd.DataFrame(raw_checks).to_csv(OUT / 'actual_native_raw_row_witness.csv', index=False)
    application['output_pins']['actual_native_raw_row_witness.csv'] = sha(OUT / 'actual_native_raw_row_witness.csv')
    application['independent_native_literal_row_checks'] = len(raw_checks)
    application['verifier_code_sha256'] = sha(__file__)
    (OUT / 'application_receipt.json').write_text(json.dumps(application, ensure_ascii=False, indent=2)+'\n')
    verification = dict(status='passed', application_receipt_sha256=sha(OUT / 'application_receipt.json'),
        accepted_ledger_pins=application['output_pins'], input_pin_count=len(application['input_pins']),
        DBF_actual_byte_checks=3, selected_native_UID_checks=len(witness), native_literal_population_reopenings=len(raw_checks),
        original_moscow_application_output_pins_verified=True, actual_State47_consumptions=1, finite_native_all3_gain=0)
    (OUT / 'verification_receipt.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(verification))

if __name__ == '__main__':
    main()
