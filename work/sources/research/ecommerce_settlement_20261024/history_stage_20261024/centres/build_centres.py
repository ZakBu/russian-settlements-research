"""Independent administrative-centre register linkage; never inferred shopping centres.
Run: PYTHONPATH=/tmp/ecommerce_audit_20261024_pyarrow python3 build_centres.py
Inputs are Rosstat raw CSV vintages and accepted census2021 source identities.
"""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import csv
import hashlib
import json
import re
import unicodedata
import pyarrow as pa
import pyarrow.parquet as pq

OUT = Path(__file__).resolve().parent
BASE = OUT.parent.parent
RAW = OUT/'raw'
longpath = BASE/'pilot/inputs/data/population/settlements_census_long.parquet'
axispath = BASE/'national/national_target_source2021.parquet'
inventorypath = BASE/'national/all_physical_source2021_inventory.parquet'
axis = pq.read_table(axispath).to_pylist()
target = {r['source_record_id_2021']:r for r in axis}
inventory = {r['source_record_id_2021'] for r in pq.read_table(inventorypath).to_pylist()}
census = [r for r in pq.read_table(longpath).to_pylist()
          if r['census_year']==2021 and r['source_record_id'] in inventory]
fields = ['TER','KOD1','KOD2','KOD3','KC','RAZDEL','NAME1','Centrum',
          'NomDescr','NomAkt','Status','DateUtv','DateVved']


def norm(s):
    s = unicodedata.normalize('NFKC',s or '').casefold().replace('ё','е')
    return re.sub(r'\s+',' ',re.sub(r'[^\w\s-]',' ',s)).strip()


def parse_name(s):
    parts = s.strip().split(maxsplit=1)
    prefix = parts[0].lower().strip('.') if parts else ''
    types = {'г':'город','с':'село','д':'деревня','п':'поселок','рп':'пгт',
             'пгт':'пгт','гп':'пгт','кп':'пгт','дп':'пгт','х':'хутор',
             'ст-ца':'станица','аул':'аул','сл':'слобода','нп':'населенный пункт',
             'ст':'станция','рзд':'разъезд','у':'улус','починок':'починок'}
    if prefix not in types or len(parts)!=2:
        return '', '', False
    return norm(parts[1]),types[prefix],True


def census_code(r):
    value = str(r['oktmo'] or '').strip()
    return value.zfill(11) if value.isdigit() and len(value) in [10,11] else ''


def write_csv(name,rows):
    if not rows:
        return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


bycode=defaultdict(list)
for r in census:
    if census_code(r): bycode[census_code(r)].append(r)
summaries=[]
settlement_layer={r['source_record_id_2021']:{k:r[k] for k in [
    'source_record_id_2021','root_accepted20261022','name_2021','type_2021','region_2021',
    'population_2021','accepted_latitude_2021','accepted_longitude_2021']}
    for r in axis}
input_manifest=[]
for path in sorted(RAW.glob('data-*.csv')):
    data=path.read_bytes()
    try: text=data.decode('utf-8-sig');encoding='utf-8'
    except UnicodeDecodeError: text=data.decode('cp1251');encoding='cp1251'
    raw=list(csv.reader(text.splitlines(),delimiter=';'))
    assert all(len(r)==13 for r in raw)
    register=[dict(zip(fields,r),source_row=i+1) for i,r in enumerate(raw)
              if all(r[j].isdigit() for j in range(4))]
    vintage=re.search(r'data-(\d{8})T',path.name).group(1)
    snapshot_date=datetime.strptime(vintage,'%Y%m%d').date()
    future_rows=[r for r in register if re.fullmatch(r'\d{2}\.\d{2}\.\d{4}',r['DateVved']) and
                 datetime.strptime(r['DateVved'],'%d.%m.%Y').date()>snapshot_date]
    register=[r for r in register if r not in future_rows]
    url='https://rosstat.gov.ru/opendata/7708234640-oktmo/'+path.name
    for r in register:
        r['code11']=''.join(r[f] for f in fields[:4])
        r['code8']=r['code11'][:8]
        r['name_norm'],r['type_norm'],r['name_parseable']=parse_name(r['NAME1'])
    np_rows=[r for r in register if r['RAZDEL']=='2' and r['KOD3']!='000']
    np_bycode={r['code11']:r for r in np_rows}
    assert len(np_bycode)==len(np_rows)
    official_names=defaultdict(list)
    for r in np_rows:
        if r['name_parseable']:
            official_names[(r['TER'],r['name_norm'],r['type_norm'])].append(r)
    np_to_census={}
    for r in np_rows:
        matched=[c for c in bycode.get(r['code11'],[]) if
                 norm(c['settlement_name'])==r['name_norm'] and
                 c['type_norm']==r['type_norm']]
        if len(matched)==1:
            np_to_census[r['code11']]=matched[0]
    upper=[r for r in register if r['RAZDEL']=='1' and r['KOD1']!='000' and
           r['KOD2']=='000' and r['KOD3']=='000']
    centre_links=[]
    for r in upper:
        cn,ct,parseable=parse_name(r['Centrum'])
        candidates=official_names.get((r['TER'],cn,ct),[]) if parseable else []
        inside=[c for c in candidates if c['code11'][:5]==r['code11'][:5]]
        chosen=inside[0] if len(inside)==1 else candidates[0] if len(candidates)==1 else None
        official_status=('unique_exact_name_type_inside_parent' if len(inside)==1 else
                         'unique_exact_name_type_in_region_external_centre' if len(candidates)==1 else
                         'ambiguous_name_type' if candidates else
                         'unparseable_or_empty_centre' if not parseable else 'no_matching_register_np')
        c=np_to_census.get(chosen['code11']) if chosen else None
        status='accepted_exact_code_name_type_census2021' if c else (
               'official_np_resolved_no_exact_census2021_link' if chosen else 'unresolved_official_centre')
        centre_links.append({
            'register_vintage':vintage,'municipality_oktmo8':r['code8'],
            'municipality_name':r['NAME1'],'administrative_centre_raw':r['Centrum'],
            'official_centre_name':chosen['NAME1'] if chosen else '',
            'official_centre_oktmo11':chosen['code11'] if chosen else '',
            'official_centre_resolution':official_status,'link_status':status,
            'source_record_id_2021':c['source_record_id'] if c else '',
            'centre_in_main_target':c['source_record_id'] in target if c else False,
            'centre_census_name':c['settlement_name'] if c else '',
            'centre_region_2021':c['region_norm'] if c else '',
            'official_centres_can_be_external':bool(chosen and chosen['code11'][:5]!=r['code11'][:5]),
            'official_date_introduced':r['DateVved'],'source_row':r['source_row'],
            'source_url':url,'interpretation':'administrative_centre_not_empirical_shopping_centre'})
    topmap={r['municipality_oktmo8']:r for r in centre_links}
    members=[]
    for c in census:
        code=census_code(c)
        official=np_bycode.get(code)
        exact=bool(official and norm(c['settlement_name'])==official['name_norm'] and
                   c['type_norm']==official['type_norm'] and np_to_census.get(code)==c)
        parent=topmap.get(code[:5]+'000') if exact else None
        linked=bool(parent and parent['source_record_id_2021'])
        members.append({
            'register_vintage':vintage,'source_record_id_2021':c['source_record_id'],
            'name_2021':c['settlement_name'],'type_2021':c['type_norm'],
            'region_2021':c['region_norm'],'census2021_oktmo11':code,
            'in_main_target':c['source_record_id'] in target,
            'np_register_link_status':'exact_code_name_type' if exact else 'no_exact_code_name_type',
            'municipality_oktmo8':parent['municipality_oktmo8'] if parent else '',
            'municipality_name':parent['municipality_name'] if parent else '',
            'administrative_centre_source_record_id_2021':parent['source_record_id_2021'] if linked else '',
            'centre_in_main_target':parent['centre_in_main_target'] if linked else False,
            'administrative_role':'centre' if linked and parent['source_record_id_2021']==c['source_record_id'] else
                                  'other_member' if linked else 'unknown',
            'context_status':'accepted_administrative_parent_and_centre' if linked else 'unknown',
            'context_is_shopping_catchment':False})
    write_csv(f'centres_{vintage}.csv',centre_links)
    write_csv(f'members_axis2021_{vintage}.csv',members)
    main=[r for r in members if r['in_main_target']]
    summary={'vintage':vintage,'raw_rows':len(raw),'effective_rows':len(register),
             'future_effective_rows_excluded':len(future_rows),'encoding':encoding,
             'official_np_rows':len(np_rows),'upper_register_rows_including_group_headers':len(upper),
             'upper_with_centre_string':sum(bool(r['administrative_centre_raw']) for r in centre_links),
             'centre_link_status':dict(Counter(r['link_status'] for r in centre_links)),
             'official_centre_resolution':dict(Counter(r['official_centre_resolution'] for r in centre_links)),
             'distinct_main_target_centres':len({r['source_record_id_2021'] for r in centre_links if r['centre_in_main_target']}),
             'main_target_np_register_link_status':dict(Counter(r['np_register_link_status'] for r in main)),
             'main_target_context_status':dict(Counter(r['context_status'] for r in main)),
             'main_target_roles':dict(Counter(r['administrative_role'] for r in main)),
             'exact_np_to_census2021_links':len(np_to_census),
             'source_url':url,'sha256':hashlib.sha256(data).hexdigest()}
    summaries.append(summary)
    centre_counts=Counter(r['source_record_id_2021'] for r in centre_links if r['source_record_id_2021'])
    for r in main:
        identifier=r['source_record_id_2021']
        row=settlement_layer[identifier]
        row[f'admin_centre_positive_{vintage}']=identifier in centre_counts
        row[f'admin_centre_municipalities_n_{vintage}']=centre_counts[identifier]
        row[f'centre_flag_interpretation_{vintage}']='positive_evidence_not_confirmed_negative'
        for col in ['np_register_link_status','municipality_oktmo8','municipality_name',
                    'administrative_centre_source_record_id_2021','context_status','administrative_role']:
            row[col+'_'+vintage]=r[col]
    input_manifest.append({'path':str(path.relative_to(OUT)),'sha256':summary['sha256'],
                           'bytes':len(data),'url':url})
    assert len(main)==144151
    assert len({r['source_record_id_2021'] for r in main})==144151
    assert all(r['context_is_shopping_catchment'] is False for r in members)
layer=list(settlement_layer.values())
census_by_id={r['source_record_id']:r for r in census}
for r in layer:
    for summary in summaries:
        vintage=summary['vintage']
        centre_id=r['administrative_centre_source_record_id_2021_'+vintage]
        r['administrative_centre_name_2021_'+vintage]=census_by_id.get(centre_id,{}).get('settlement_name','')
    group20=r['municipality_oktmo8_20200110']
    group21=r['municipality_oktmo8_20211103']
    centre20=r['administrative_centre_source_record_id_2021_20200110']
    centre21=r['administrative_centre_source_record_id_2021_20211103']
    r['admin_code_and_centre_stable_2020_2021_candidate']=bool(
        group20 and group20==group21 and centre20 and centre20==centre21)
    r['unchanged_boundaries_verified']=False
pq.write_table(pa.Table.from_pylist(layer),OUT/'settlement_admin_context_main2021.parquet',compression='zstd')
assert len(layer)==len(set(settlement_layer))==144151
for p in [axispath,inventorypath,longpath]:
    input_manifest.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
result={'status':'PASS_with_explicit_unmatched','run_date':'2026-10-24',
        'source':'Rosstat official OKTMO open-data archive, upper municipal units only',
        'linkage':'Official centre raw name/type -> unique same-name/type NP inside municipality, otherwise unique in classifier region; then exact NP code/name/type -> unique census2021 physical source row. No nearest-point or marketplace inputs.',
        'important':'Administrative context is not a shopping/service catchment. Vintages are the registered municipal state; no automatic continuity across reforms or unchanged boundaries.',
        'summaries':summaries,'inputs':input_manifest,
        'settlement_layer':'settlement_admin_context_main2021.parquet',
        'settlement_layer_rows':len(layer),
        'stable_code_centre2020_2021_candidate_n':sum(r['admin_code_and_centre_stable_2020_2021_candidate'] for r in layer)}
(OUT/'audit_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summaries,ensure_ascii=False,indent=2))
