"""Stage the checked historical-code/spatial identity rule on exact source rows.

The staged graph must receive an independent application decision. Population,
coordinates and boundary comparability are never admitted by this application.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import zipfile
import pandas as pd
import xlrd
from lxml import html, etree
from .apply_identity_rules import _metadata, _require_origin, _verified_direct_context, _norm, _sha
from .recover_admin_context import SHEET_PROFILES
from .candidate_graph_checks import _load_nodes, YearConstrainedUnionFind, AGGREGATE_SCOPES

ROOT = Path('/workspace/settlements-work')
SELECTED = Path('/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet')

def region_key(value):
    text=re.sub(r'[-–—]+',' ',_norm(value))
    aliases={'рсо':'северная осетия алания','кчр':'карачаево черкесская','кбр':'кабардино балкарская',
             'якутия':'саха якутия','удмуртия':'удмуртская','чувашия':'чувашская','нижегород':'нижегородская',
             'чувашская республика чувашия':'чувашская'}
    text=aliases.get(' '.join(text.split()),text)
    text=re.sub(r'^республика\s+','',text)
    text=re.sub(r'\s+(область|обл\.?|край|края|республика|респ\.?|автономный округ|автономная область)$','',text)
    return ' '.join(text.split())

def typed_source_label_matches(raw, typ, name):
    label=_norm(raw);name=_norm(name);typ=_norm(typ)
    aliases={'д':'деревня','дер':'деревня','деревня':'деревня','с':'село','село':'село',
             'п':'поселок','пос':'поселок','поселок':'поселок','х':'хутор','хутор':'хутор',
             'ст-ца':'станица','станица':'станица','ст':'станция','станция':'станция',
             'рзд':'разъезд','разъезд':'разъезд','слобода':'слобода','г':'город','город':'город'}
    for prefix,canonical in sorted(aliases.items(),key=lambda p:-len(p[0])):
        match=re.match(r'^'+re.escape(prefix)+r'(?:\.\s*|\s+)(.+)$',label)
        if match and canonical==aliases.get(typ,typ) and match.group(1)==name:return True
    return label==typ+' '+name

def source_profiles():
    profiles = {key: dict(value) for key, value in SHEET_PROFILES.items()}
    for prefix, row in [('010_',4),('011_',3),('013_',3)]:
        for file in Path('/workspace/settlements-raw/data/raw/2010').glob(prefix+'*.xls'):
            profiles['data/raw/2010/'+file.name] = {'sheet':'Data Sheet','header_row':row,
                'first_data_row':7 if prefix=='010_' else 6,'region_col':2,
                'district_cols':[], 'name_cols':[3], 'population_col':4,
                'headers':{4:'Всего'}}
    # These sheets declare one subject throughout; the name and count cells
    # are explicit and no district propagation is performed.
    for prefix,sheet,reg in [('015_','komi','Коми'),('018_','2010','Дагестан'),('019_','Data Sheet','Тверская область')]:
        for file in Path('/workspace/settlements-raw/data/raw/2010').glob(prefix+'*.xls'):
            dag = prefix=='018_'
            profiles['data/raw/2010/'+file.name] = {'sheet':sheet,'header_row':4,
                'first_data_row':6 if dag else 7, 'region_constant':reg,
                'district_cols':[], 'name_cols':[9 if dag else 2],
                'population_col':8 if dag else 3,
                'headers':{7:'название',8:'2010.0'} if dag else {3:'Всего' if prefix=='015_' else 'Total'},
                'type_name_columns':(6,7) if dag else None}
    return profiles

def verify_source_rows(metadata, source_binds, raw_root):
    profiles=source_profiles(); groups=defaultdict(list); checks={}
    for sid, row in metadata.items():
        if row['census_year']==2010:
            groups[row['source_file']].append((sid,row))
    for file, rows in groups.items():
        if file not in profiles:
            for sid,row in rows: checks[sid]={'status':'held_source_family_not_yet_applied','source_file':file}
            continue
        profile=profiles[file];path=raw_root/file
        if not path.is_file() or _sha(path)!=source_binds[file]['sha256']:
            raise ValueError('Source bytes mismatch '+file)
        book=xlrd.open_workbook(str(path),on_demand=True);sheet=book.sheet_by_name(profile['sheet'])
        for col,expected in profile['headers'].items():
            if _norm(sheet.cell_value(profile['header_row']-1,int(col)))!=_norm(expected):
                raise ValueError('Source header changed '+file)
        const=profile.get('region_constant')
        if profile.get('region_constant_cell'):
            r,c=profile['region_constant_cell'];const=sheet.cell_value(r-1,c)
        for sid, row in rows:
            number=row.get('source_row')
            if number is None or pd.isna(number) or int(number)<profile['first_data_row'] or int(number)>sheet.nrows:
                checks[sid]={'status':'held_raw_row_outside_profile'};continue
            values=sheet.row_values(int(number)-1)
            if profile.get('type_name_columns'):
                t,n=profile['type_name_columns'];values += ['']*max(0,10-len(values));values[9]=str(values[t])+' '+str(values[n])
            raw_labels=[str(values[i]).strip() for i in profile['name_cols'] if str(values[i]).strip()]
            labels=raw_labels+[' '.join(raw_labels)]
            raw_label=next((label for label in labels if typed_source_label_matches(label,row['settlement_type'],row['settlement_name'])),None)
            region=values[profile['region_col']] if profile.get('region_col') is not None else const
            raw_pop=values[profile['population_col']]
            if raw_label is None:error='raw_label_mismatch'
            elif pd.isna(raw_pop) or not isinstance(raw_pop,(int,float)) or raw_pop!=row['population']:error='raw_population_mismatch'
            elif region_key(region)!=region_key(row['region_raw']):error='raw_region_mismatch'
            else:error=None
            checks[sid]={'status':'held_'+error if error else 'raw_row_exact_label_population_region_verified',
                         'source_file':file,'source_sha256':source_binds[file]['sha256'],
                         'source_sheet':profile['sheet'],'source_row_1based':int(number),
                         'raw_label':raw_label or ' | '.join(raw_labels),'raw_population':str(raw_pop),
                         'raw_region':str(region),'selected_region':row['region_raw'],
                         'district_carry_used':False}
        book.release_resources()
    # Arkhangelsk uses a full HTML table row locator rather than source_row.
    ark=Path('/workspace/settlements-work/sources/r2-missing/arkhangelsk_2010_archived_original.html')
    ark_files=[f for f in groups if 'arkhangelsk_2010_archived_original.html' in f]
    if ark_files:
        ark_sha=_sha(ark)
        table_rows=html.fromstring(ark.read_bytes()).xpath('//table')[0].xpath('.//tr')
        for file in ark_files:
            if ark_sha!=source_binds[file]['sha256']:raise ValueError('Ark raw hash mismatch')
            for sid,row in groups[file]:
                match=re.search(r'source row (\d+)',str(row.get('source_locator')))
                if not match:continue
                nr=int(match.group(1));cells=[' '.join(''.join(c.itertext()).split()) for c in table_rows[nr-1].xpath('./td|./th')]
                label=row.get('source_name_raw') or row.get('settlement_name')
                ok=len(cells)>=2 and _norm(cells[0])==_norm(label) and cells[1].replace(' ','')==str(int(row['population']))
                checks[sid]={'status':'raw_row_exact_label_population_region_verified' if ok else 'held_ark_raw_mismatch',
                             'source_file':file,'source_sha256':ark_sha,'source_row_1based':nr,
                             'source_region_context':'Arkhangelsk pinned regional publication; selected R2 source join',
                             'raw_label':cells[0],'raw_population':cells[1], 'district_carry_used':False}
    karelia=Path('/workspace/settlements-karelia-inputs/build/evidence/ingestion/source/karelia_2010_rural_settlements.docx')
    docx_files=[f for f in groups if f.endswith('karelia_2010_rural_settlements.docx')]
    if docx_files:
        from research_rebuild.ingestion.extract_karelia_rural_2010_docx import visible_xml_text
        doc_sha=_sha(karelia)
        with zipfile.ZipFile(karelia) as zipped:doc=etree.fromstring(zipped.read('word/document.xml'))
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        tables=doc.xpath('./w:body/w:tbl',namespaces=ns)
        for file in docx_files:
            if doc_sha!=source_binds[file]['sha256']:raise ValueError('Karelia DOCX source mismatch')
            for sid,row in groups[file]:
                match=re.fullmatch(r'table\[(\d+)\]\.row\[(\d+)\]',str(row.get('source_locator')))
                if not match:continue
                ti,ri=map(int,match.groups());raw_row=tables[ti].xpath('./w:tr',namespaces=ns)[ri]
                cells=[visible_xml_text(cell) for cell in raw_row.xpath('./w:tc',namespaces=ns)]
                ok=len(cells)>=2 and typed_source_label_matches(cells[0],row['settlement_type'],row['settlement_name']) and cells[1].replace(' ','')==str(int(row['population'])) and region_key(row['region_raw'])=='карелия'
                checks[sid]={'status':'raw_row_exact_label_population_region_verified' if ok else 'held_karelia_raw_mismatch',
                             'source_file':file,'source_sha256':doc_sha,'source_locator':row['source_locator'],
                             'raw_label':cells[0],'raw_population':cells[1],
                             'selected_source_name_raw_original':str(row.get('source_name_raw')),
                             'source_label_metadata_discrepancy':_norm(cells[0])!=_norm(row.get('source_name_raw')),
                             'original_source_transport_tls_limitation_retained':True,'district_carry_used':False}
    return checks

def relevant_events(events, keys, start=2010, end=2021):
    found=[]
    for event in events:
        if not keys.intersection({event.get('from_settlement_id_legacy_candidate'),event.get('to_settlement_id_legacy_candidate')}):continue
        date=str(event.get('source_asserted_effective_date') or '')
        match=re.match(r'(\d{4})',date)
        year=int(match.group(1)) if match else None
        if year is not None and not start<=year<=end:continue
        typ=event.get('event_type','')
        if typ in {'renamed','status_changed','boundary_change'}:continue
        if year is None and str(event.get('event_id','')).startswith('coverage:2002:'):continue
        found.append(event['event_id'])
    return found

def run(output, review):
    if output.exists():raise FileExistsError('New immutable output required')
    review_data=json.loads(review.read_text())
    candidate_path=ROOT/'candidates/historical_spatial_v1/identity_candidates.parquet'
    candidate_sha=_sha(candidate_path);review_sha=_sha(review)
    if review_data.get('review_id')!='historical_spatial_rule_review_2026-10-03_v2' or not review_data.get('verdict','').startswith('CONDITIONAL APPROVE'):
        raise ValueError('Unrecognized scientific rule review')
    sample_receipt=json.loads((review.parent/'sample_receipt.json').read_text())
    pins=sample_receipt['pinned_inputs']
    candidate_receipt=ROOT/'candidates/historical_spatial_v1/receipt.json'
    if _sha(candidate_receipt)!=pins['historical_spatial_v1_receipt_sha256'] or _sha(SELECTED)!=pins['selected_2010_2021_sha256']:
        raise ValueError('Frozen candidate/source pins changed')
    if candidate_sha!=json.loads(candidate_receipt.read_text())['outputs'][candidate_path.name]:raise ValueError('Candidate output changed')
    base_path=ROOT/'identity/accepted_ordinary_v4/accepted_identity_edges.parquet'
    evidence=ROOT/'candidates/optimized_run/source_evidence.parquet'
    manifest=Path('/workspace/settlements-baseline/output/input_manifest.parquet')
    c=pd.read_parquet(candidate_path);c=c[c.historical_spatial_rule_candidate].copy()
    endpoints=set(c.from_source_record_id)|set(c.to_source_record_id)
    metadata,binds=_metadata(SELECTED,endpoints,manifest)
    checks=verify_source_rows(metadata,binds,Path('/workspace/settlements-raw'))
    nodes,_=_load_nodes(SELECTED,evidence);graph=YearConstrainedUnionFind(nodes)
    base=pd.read_parquet(base_path);graph.initialize_edges(zip(base.from_source_record_id,base.to_source_record_id))
    base_pairs={tuple(sorted((a,b))) for a,b in zip(base.from_source_record_id,base.to_source_record_id)}
    selected_ids=pd.read_parquet(SELECTED,columns=['source_record_id','settlement_id','oktmo']).set_index('source_record_id').to_dict('index')
    events_path=ROOT/'sources/historical_identifiers/observed_v1/lineage_event_candidates.json'
    events=json.loads(events_path.read_text());ledger=[];new=[]
    for row in c.sort_values(['from_source_record_id','to_source_record_id']).to_dict('records'):
        a,b=row['from_source_record_id'],row['to_source_record_id'];reasons=[]
        for sid in [a,b]:
            meta=metadata[sid];node=nodes[sid]
            if node.aggregate or not meta['is_additive_settlement_record'] or meta['population_scope'] in AGGREGATE_SCOPES:reasons.append('nonsettlement_or_aggregate')
            if not _require_origin(meta):reasons.append('source_origin_not_traceable')
        if checks[a]['status']!='raw_row_exact_label_population_region_verified':reasons.append(checks[a]['status'])
        if row['legacy_identity_conflict_present'] or row['legacy_same_year_collision_present']:reasons.append('unresolved_legacy_identity_conflict')
        keys=set()
        for sid in [a,b]:
            for field in ['settlement_id','oktmo']:
                val=selected_ids[sid][field]
                if isinstance(val,str) and val:keys.add(val if field=='settlement_id' else 'RU-OKTMO-'+val)
        event_ids=relevant_events(events,keys)
        if event_ids:reasons.append('relevant_code_keyed_event_unresolved')
        status='held';effect='not_applied';pair=tuple(sorted((a,b)))
        if not reasons:
            effect,overlap,_,_=graph.add_edge(a,b)
            if effect=='blocked_same_year_component_collision':reasons.append('same_year_graph_collision')
            elif pair in base_pairs:status='existing_pair_corroboration'
            else:
                status='staged_checked_rule_application';edge={col:None for col in base.columns}
                edge.update(decision_id='HIST-'+row['candidate_id'],relation='same_place',from_source_record_id=a,from_year='2010',
                    to_source_record_id=b,to_year='2021',decision_status='pending_independent_application_review',
                    decision_rule='exact_named_historical_code_spatial_rule_v2',evidence_sha256=candidate_sha,
                    selection_projection_status='active_endpoints_selected',graph_connectivity_effect=effect,
                    rule_review_sha256=review_sha,source_application_check_json=json.dumps(checks[a],ensure_ascii=False),
                    population_quality_changed=False,coordinate_admitted=False,boundary_comparability_asserted=False)
                new.append(edge)
        ledger.append({'from_source_record_id':a,'to_source_record_id':b,'candidate_id':row['candidate_id'],
                       'status':status,'graph_connectivity_effect':effect,'hold_reasons_json':json.dumps(reasons),
                       'event_ids_json':json.dumps(event_ids),'raw_row_check_status':checks[a]['status']})
    output.mkdir(parents=True)
    pd.DataFrame(ledger).to_parquet(output/'application_checks.parquet',index=False)
    pd.DataFrame(checks).T.reset_index(names='source_record_id').to_parquet(output/'source_row_checks.parquet',index=False)
    merged=pd.concat([base,pd.DataFrame(new)],ignore_index=True)
    merged.to_parquet(output/'staged_identity_edges.parquet',index=False)
    receipt={'status':'staged_pending_independent_application_review','candidate_rows':len(c),'new_staged_pairs':len(new),
             'application_status_counts':dict(Counter(x['status'] for x in ledger)),
             'raw_row_check_counts':dict(Counter(x['status'] for x in checks.values())),
             'input_hashes':{str(p):_sha(p) for p in [SELECTED,candidate_path,base_path,evidence,review,events_path]},
             'output_hashes':{p.name:_sha(p) for p in output.glob('*.parquet')},'builder_sha256':_sha(Path(__file__)),
             'limits':'Identity only; no population/coordinate/boundary admissions. Unapplied source families held, not declared missing.'}
    (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k.endswith('counts') or k in ['status','new_staged_pairs','candidate_rows']},ensure_ascii=False))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--review',type=Path,required=True)
    a=p.parse_args();run(a.output,a.review)
if __name__=='__main__':main()
