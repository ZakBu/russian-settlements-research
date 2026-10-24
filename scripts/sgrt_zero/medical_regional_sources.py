#!/usr/bin/env python3
"""Lossless, dated normalization of official FFOMS XML registries from a TFOMS mirror.

No geocoding, care inference, closure inference or address substitution is performed.
Original historical rows are retained; an inclusive validity screen creates separate
current files. Blank/invalid dates are explicitly unknown and excluded from current.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import hashlib
from functools import lru_cache
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import shutil

SOURCE_URL = 'http://www.xn--j1adfnaco.xn--p1ai/files/nsi/SpravNSI.zip'
ARCHIVE_SHA256 = 'e7bab4fa92ba0273faf18d6bfb97c368c3fd0b66290c3b2a82d82bc47ff6db42'


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def records(path):
    context = ET.iterparse(path, events=('start', 'end'))
    _, root = next(context)
    for event, el in context:
        if event == 'end' and el.tag.lower() == 'zap':
            yield {c.tag: c.text for c in el}
            root.clear()


@lru_cache(maxsize=65536)
def date_value(value):
    if not value:
        return None
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def validity(row, asof):
    begin, end = date_value(row.get('DATEBEG')), date_value(row.get('DATEEND'))
    if begin is None or end is None:
        return 'unknown_validity'
    if begin > end:
        return 'invalid_interval'
    return 'valid_at_snapshot' if begin <= asof <= end else 'outside_snapshot_interval'


def header(path):
    for event, el in ET.iterparse(path, events=('end',)):
        if el.tag.lower() == 'zglv':
            return {c.tag: c.text for c in el}
    return {}


def normalize(input_dir, output, asof, codes=('F032', 'F033', 'F034', 'F038')):
    import pyarrow as pa
    import pyarrow.parquet as pq
    output.mkdir(parents=True, exist_ok=True)
    summary = {'source_url': SOURCE_URL, 'original_archive_sha256': ARCHIVE_SHA256,
               'asof': str(asof), 'inclusive_record_validity_not_closure': True,
               'source_role': 'official_territorial_fund_mirror_of_federal_registries',
               'address_semantics': 'F038.ADDR=care_location; F032.JURADDRESS_ADDRESS=legal_only',
               'registries': {}}
    for code in codes:
        path = input_dir / (code + '.xml')
        # Discover every source field before fixing an all-string Parquet schema.
        fields = sorted({k for row in records(path) for k in row})
        schema = pa.schema([(k, pa.string()) for k in fields] + [
            ('record_validity_status', pa.string()), ('source_registry', pa.string()),
            ('source_snapshot_date', pa.string()), ('source_record_row', pa.string())])
        metadata = header(path)
        snapshot = metadata.get('DATE') or metadata.get('date')
        writers = {kind: pq.ParquetWriter(output / f'{code}_{kind}.parquet', schema, compression='zstd')
                   for kind in ('history', 'current')}
        counts = collections.Counter(); region = collections.Counter(); batch = []
        def write_batch(rows):
            writers['history'].write_table(pa.Table.from_pylist(rows, schema=schema))
            current = [r for r in rows if r['record_validity_status'] == 'valid_at_snapshot']
            if current:
                writers['current'].write_table(pa.Table.from_pylist(current, schema=schema))
        for n, row in enumerate(records(path), 1):
            status = validity(row, asof); counts[status] += 1
            row.update(record_validity_status=status, source_registry=code,
                       source_snapshot_date=snapshot, source_record_row=str(n))
            batch.append(row)
            if status == 'valid_at_snapshot':
                region[(row.get('UIDMO') or row.get('UIDSPMO') or '')[:2]] += 1
            if len(batch) == 10000:
                write_batch(batch); batch = []
        if batch:
            write_batch(batch)
        for w in writers.values():
            w.close()
        summary['registries'][code] = {'xml_sha256': digest(path), 'header': metadata,
             'fields': fields, 'row_validity_counts': dict(counts),
             'current_territorial_uid_prefix_counts': dict(sorted(region.items())),
             'outputs': {k: {'path': str(output/f'{code}_{k}.parquet'),
                            'sha256': digest(output/f'{code}_{k}.parquet')}
                         for k in ('history', 'current')}}
        print(code, dict(counts), flush=True)
    # Preserve dictionaries exactly: attributes carry the source's numeric care codes.
    for code in ('V002', 'V006', 'V008'):
        path = input_dir / (code + '.xml')
        tree = ET.parse(path)
        rows = [dict(el.attrib) for el in tree.iter() if el.attrib]
        (output / (code + '_codebook.json')).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf8')
    (output / 'source_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    return summary



def join_current(output, asof=dt.date(2026,10,23)):
    """Exact care-site joins with cardinality checks; never substitute legal addresses."""
    import duckdb
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'")
    for code in ('F032', 'F033', 'F034', 'F038'):
        path = str(output / f'{code}_current.parquet').replace("'", "''")
        con.execute(f"CREATE VIEW {code} AS SELECT * FROM read_parquet('{path}')")
    audit = {}
    for code, keys in [('F032','UIDMO'), ('F033','UIDSPMO'), ('F038','UIDSPMO, IDADDRESS')]:
        duplicates = con.execute(f"SELECT count(*) FROM (SELECT {keys},count(*) n FROM {code} GROUP BY {keys} HAVING count(*)>1)").fetchone()[0]
        audit[code + '_duplicate_join_keys'] = duplicates
        if duplicates:
            raise ValueError(f'{code}: {duplicates} ambiguous join keys; no arbitrary deduplication')
    audit['F034_duplicate_evidence_keys'] = con.execute("SELECT count(*) FROM (SELECT UIDSPMO,IDADDRESS,MPVID,MPUSL,MPROF,count(*) n FROM F034 GROUP BY ALL HAVING count(*)>1)").fetchone()[0]
    asof_literal = str(asof)
    # Select names and literal service address; all individual source intervals retained.
    con.execute(f"""CREATE VIEW joined AS SELECT v.*,
      s.NAM_SPMO,s.NAM_SK_SPMO,s.VID_SPMO,s.OID_SPMO,
      a.ADDR,a.ADDR_GAR,a.N_DOC,a.UIDMO,
      m.NAM_MOP,m.NAM_MOK,m.NAM_MOP AS organization_name,
      m.SUBJ AS organization_participation_subject,m.VID_MO,m.OID_MO,m.INN,m.OGRN,m.MCOD,m.VEDPRI,
      m.D_BEGIN_OMS,m.D_END,m.NAME_E,
      CASE WHEN m.UIDMO IS NULL THEN NULL
           WHEN try_strptime(m.D_END,'%d.%m.%Y') <= DATE '{asof_literal}' THEN TRUE
           ELSE FALSE END AS organization_oms_participation_ended_asof,
      CASE WHEN m.UIDMO IS NULL THEN 'organization_unmatched'
           WHEN m.D_END IS NOT NULL AND try_strptime(m.D_END,'%d.%m.%Y') IS NULL THEN 'participation_end_date_unknown'
           WHEN try_strptime(m.D_END,'%d.%m.%Y') <= DATE '{asof_literal}' THEN 'oms_participation_ended_not_closure'
           WHEN try_strptime(m.D_BEGIN_OMS,'%d.%m.%Y') > DATE '{asof_literal}' THEN 'oms_participation_not_started'
           ELSE 'no_recorded_oms_exclusion_asof' END AS organization_oms_participation_status,
      s.DATEBEG AS subdivision_valid_from,s.DATEEND AS subdivision_valid_to,
      a.DATEBEG AS care_address_valid_from,a.DATEEND AS care_address_valid_to,
      m.DATEBEG AS organization_valid_from,m.DATEEND AS organization_valid_to,
      s.UIDSPMO IS NOT NULL AS subdivision_exact_join,
      a.IDADDRESS IS NOT NULL AS care_address_exact_pair_join,
      m.UIDMO IS NOT NULL AS organization_exact_join,
      CASE WHEN a.IDADDRESS IS NULL THEN 'care_address_unmatched'
           WHEN a.ADDR IS NULL THEN 'care_address_literal_missing'
           ELSE 'literal_care_address_available' END AS care_location_status
      FROM F034 v LEFT JOIN F033 s ON v.UIDSPMO=s.UIDSPMO
      LEFT JOIN F038 a ON v.UIDSPMO=a.UIDSPMO AND v.IDADDRESS=a.IDADDRESS
      LEFT JOIN F032 m ON a.UIDMO=m.UIDMO""")
    audit['join_counts'] = con.execute("SELECT count(*),count(*) FILTER(WHERE subdivision_exact_join),count(*) FILTER(WHERE care_address_exact_pair_join),count(*) FILTER(WHERE organization_exact_join) FROM joined").fetchone()
    audit['join_count_fields'] = ['profile_rows','subdivision_matched','address_pair_matched','organization_matched']
    audit['all_current_profiles_retained'] = audit['join_counts'][0] == con.execute('SELECT count(*) FROM F034').fetchone()[0]
    target = str(output/'care_site_profiles_current.parquet').replace("'", "''")
    con.execute(f"COPY joined TO '{target}' (FORMAT PARQUET,COMPRESSION ZSTD)")
    audit['output_sha256'] = digest(output/'care_site_profiles_current.parquet')
    (output/'join_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    print('JOIN',audit,flush=True)
    return audit


def extract_archive(archive, destination):
    """Extract only required official dictionaries, after verifying immutable source."""
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError('Source archive SHA256 differs from reviewed 23.10.2026 snapshot')
    needed = {c+'.xml' for c in ('F032','F033','F034','F038','V002','V006','V008')}
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        entries = {Path(n).name:n for n in z.namelist() if Path(n).name in needed}
        if set(entries) != needed:
            raise ValueError('Archive lacks required dictionaries')
        for name, member in entries.items():
            with z.open(member) as src, open(destination/name,'wb') as dst:
                shutil.copyfileobj(src,dst,1024*1024)
    return destination


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input-dir', type=Path)
    p.add_argument('--archive', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--asof', type=dt.date.fromisoformat, default=dt.date(2026,10,23))
    a = p.parse_args()
    if a.archive:
        a.input_dir = extract_archive(a.archive, a.input_dir or a.output/'inputs')
    if a.input_dir is None:
        p.error('--input-dir or --archive is required')
    normalize(a.input_dir, a.output, a.asof)
    join_current(a.output, a.asof)

if __name__ == '__main__':
    main()
