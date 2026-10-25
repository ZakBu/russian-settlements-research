"""Normalize dated positive Ozon archive evidence, keeping an undated XLSX separate.

PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 normalize_sources.py
No current input is changed; source absence is never encoded as physical absence.
"""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse,parse_qs
import base64,csv,gzip,hashlib,json,re,xml.etree.ElementTree as ET,zipfile
from collections import Counter

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parent
RAW=ROOT/'raw'


class StateParser(HTMLParser):
    def __init__(self):
        super().__init__();self.states=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'data-state' in attrs:
            try:self.states.append((attrs.get('id',''),json.loads(attrs['data-state'])))
            except (ValueError,TypeError):pass


def nested(obj,*keys):
    for k in keys:
        if not isinstance(obj,dict):return None
        obj=obj.get(k)
    return obj


def sha1base32(body):
    return base64.b32encode(hashlib.sha1(body).digest()).decode().rstrip('=')


def main():
    cdx={}
    for file in RAW.glob('cdx*.json'):
        if file.name.endswith('.request.json'):continue
        try:j=json.loads(file.read_bytes())
        except (ValueError,UnicodeDecodeError):continue
        if j and isinstance(j,list):
            for r in j[1:]:
                x=dict(zip(j[0],r));cdx[(x['timestamp'],x['original'])]=x
    evidence=[];page_audit=[]
    for file in sorted(RAW.glob('geo*.body')):
        receipt=json.loads(file.with_name(file.name+'.request.json').read_text())
        if receipt.get('status')!=200:continue
        match=re.search(r'/web/(\d{14})id_/(https?://.*)',receipt.get('resolved_url',''))
        if not match:continue
        timestamp,url=match.groups();date=timestamp[:4]+'-'+timestamp[4:6]+'-'+timestamp[6:8]
        body=file.read_bytes();assert hashlib.sha256(body).hexdigest()==receipt['sha256']
        expected=cdx.get((timestamp,url));archive_digest_ok=None
        if expected:
            archive_digest_ok=sha1base32(body)==expected['digest']
            assert archive_digest_ok,file.name
        decoded=gzip.decompress(body)if body[:2]==b'\x1f\x8b'else body
        parser=StateParser();parser.feed(decoded.decode('utf8','replace'))
        rows=[]
        common={'archive_date':date,'archive_timestamp':timestamp,'source_url':url,
            'archive_url':receipt['resolved_url'],'source_body':str(file.relative_to(ROOT)),
            'source_sha256':receipt['sha256'],'cdx_digest_verified':archive_digest_ok,
            'date_definition':'archive capture of positive object page, not opening date',
            'source_city_slug':urlparse(url).path.split('/')[2]if len(urlparse(url).path.split('/'))>2 else None}
        for state_id,state in parser.states:
            if not isinstance(state,dict):continue
            pvz=state.get('pvz')
            if isinstance(pvz,dict)and nested(pvz,'coordinates','latitude')is not None:
                hours=pvz.get('workingHours',[])
                dates=[x.get('date')for x in hours if x.get('date')]
                row={**common,'object_id':str(pvz['id']),'name':pvz.get('name'),
                    'address':pvz.get('address'),'latitude':nested(pvz,'coordinates','latitude'),
                    'longitude':nested(pvz,'coordinates','longitude'),
                    'provider_id':nested(pvz,'provider','id'),'provider_name':nested(pvz,'provider','name'),
                    'delivery_type_id':nested(pvz,'deliveryType','id'),
                    'delivery_type_name':nested(pvz,'deliveryType','name'),
                    'city_label':nested(state,'location','city'),'region_label':nested(state,'location','region'),
                    'source_country':nested(state,'location','countryCode'),
                    'embedded_working_hours_first_date':min(dates)if dates else None,
                    'embedded_working_hours_last_date':max(dates)if dates else None,
                    'extraction':'data-state.pvz.coordinates, never city geoCoordinate',
                    'source_state_id':state_id,'properties_json':json.dumps(pvz.get('properties'),ensure_ascii=False),
                    'opening_date':None}
                rows.append(row)
        details=[s for key,s in parser.states if 'addressEditPickUpDetailFullWeb'in key]
        maps=[(key,s)for key,s in parser.states if 'addressEditMap-'in key]
        target_match=re.search(r'/geo/[^/?]+/(\d+)',url)
        target=target_match.group(1)if target_match else None
        if target:
            for script in re.findall(r'<script[^>]*type=["\x27]application/ld\+json["\x27][^>]*>(.*?)</script>',decoded.decode('utf8','replace'),re.S):
                try:ld=json.loads(script)
                except ValueError:continue
                if isinstance(ld,dict)and ld.get('@type')=='Store'and ld.get('latitude')is not None and ld.get('longitude')is not None:
                    rows.append({**common,'object_id':target,'name':ld.get('name'),
                        'address':ld.get('address'),'latitude':float(ld['latitude']),
                        'longitude':float(ld['longitude']),'provider_id':None,'provider_name':None,
                        'delivery_type_id':None,'delivery_type_name':None,'city_label':None,
                        'region_label':None,'source_country':None,
                        'embedded_working_hours_first_date':None,'embedded_working_hours_last_date':None,
                        'extraction':'JSON-LD Store.latitude/longitude and point ID from canonical source URL',
                        'source_state_id':'script.application/ld+json','properties_json':None,'opening_date':None})
        if details and maps:
            detail=details[0]
            for state_id,state in maps:
                for pin in state.get('pins',[]):
                    coords=pin.get('coordinates',{})
                    point=parse_qs(urlparse(pin.get('link','')).query).get('pp',[None])[0]
                    if point and coords.get('latitude')is not None:
                        is_target=point==target
                        rows.append({**common,'object_id':str(point),
                            'name':nested(detail,'header','title','text')if is_target else None,
                            'address':nested(detail,'location','address','text')if is_target else None,
                            'latitude':coords['latitude'],'longitude':coords['longitude'],
                            'provider_id':None,'provider_name':None,'delivery_type_id':None,
                            'delivery_type_name':None,'city_label':None,'region_label':None,
                            'source_country':None,'embedded_working_hours_first_date':None,
                            'embedded_working_hours_last_date':None,
                            'extraction':'data-state.addressEditMap.pins.coordinates with pp identifier',
                            'source_state_id':state_id,'properties_json':None,'opening_date':None})
        for row in rows:
            assert -90<=row['latitude']<=90 and -180<=row['longitude']<=180
        evidence.extend(rows)
        page_audit.append({**common,'extracted_object_records_n':len(rows),'states_n':len(parser.states)})
    df=pd.DataFrame(evidence)
    assert len(df)>0
    df=df.drop_duplicates(['archive_timestamp','source_url','object_id']).sort_values(['archive_date','object_id'])
    assert df.latitude.notna().all()and df.longitude.notna().all()
    df.to_csv(ROOT/'ozon_archived_positive_objects.csv',index=False)
    pq.write_table(pa.Table.from_pandas(df,preserve_index=False),ROOT/'ozon_archived_positive_objects.parquet')
    pd.DataFrame(page_audit).to_csv(ROOT/'geo_page_extraction_audit.csv',index=False)
    xlsx=RAW/'krasnoyarsk_active_points_Other.xlsx'
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(xlsx)as z:
        strings=[''.join(e.itertext())for e in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        core=ET.fromstring(z.read('docProps/core.xml'))
        created=core.find('{http://purl.org/dc/terms/}created').text
        modified=core.find('{http://purl.org/dc/terms/}modified').text
        xrows=[]
        for row in sheet.find('s:sheetData',ns):
            n=int(row.attrib['r'])
            if n<=8:continue
            values={}
            for cell in row:
                value=cell.find('s:v',ns)
                if value is not None:
                    values[re.sub(r'\d','',cell.attrib['r'])]=strings[int(value.text)]if cell.attrib.get('t')=='s'else value.text
            if not values:continue
            xrows.append({'source_sheet':'Регионы','source_row':n,
                'point_type':values.get('A'),'region':values.get('B'),'city_label':values.get('C'),
                'address':values.get('D'),'technical_name':values.get('E'),'acceptance_hours':values.get('F'),
                'observation_date':None,'xlsx_core_created':created,'xlsx_core_modified':modified,
                'git_commit_date':'2026-04-16T09:45:22Z',
                'numeric_Ozon_object_id':None,'latitude':None,'longitude':None,
                'source_scope':'Пункты приёма в регионах (ПВЗ), seller acceptance subset',
                'observation_date_status':'unverified; file metadata is not observation date'})
    xd=pd.DataFrame(xrows)
    xd.to_csv(ROOT/'ozon_seller_acceptance_xlsx_undated_candidate.csv.gz',index=False,compression='gzip')
    summary={'archived_point_rows':len(df),'unique_object_ids':int(df.object_id.nunique()),
        'archive_year_counts':dict(Counter(df.archive_date.str[:4])),
        'source_city_slug_counts':dict(Counter(df.source_city_slug)),
        'provider_name_counts':dict(Counter(df.provider_name.fillna('unknown'))),
        'distinct_source_pages':int(df.source_url.nunique()),
        'geopages_successful_fetched_n':len(page_audit),
        'geo_pages_cdx_digest_verified_n':sum(x['cdx_digest_verified']is True for x in page_audit),
        'national_history_complete':False,'zero_archive_evidence_means_absence':False,
        'archive_capture_is_opening_date':False,
        'xlsx_candidate':{'rows':len(xd),'technical_names_unique':int(xd.technical_name.nunique()),
            'missing_technical_name_n':int(xd.technical_name.isna().sum()),
            'point_type_counts':dict(Counter(xd.point_type)),
            'xlsx_core_created':created,'xlsx_core_modified':modified,
            'observation_date':None,'commit_date':'2026-04-16T09:45:22Z',
            'numeric_ids_or_source_coordinates':False,
            'not_promoted_to_2025_observation':True}}
    (ROOT/'normalization_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
