"""Stream one wide row per accepted ordinary three-source-ID tuple; no backfills."""
from pathlib import Path
import csv,gzip,hashlib,json,math,time,base64

YEARS=(2002,2010,2021)
DEST=Path('/workspace/settlements-delivery/working-full-chain-20261007')
SOURCE_FIELDS=('source_record_id','settlement_name','settlement_type','region_norm','district_raw','population','population_value_quality','oktmo','okato','source_file','source_path','source_sha256','source_locator')
POINT_FIELDS=('latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_kind','point_origin_file','point_origin_sha256','point_origin_locator','point_ledger_path')

def clean(v):
    if v is None: return ''
    try:
        if v!=v: return ''
    except (TypeError,ValueError): pass
    if hasattr(v,'item'): return v.item()
    return v

def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def build(state,ordinary,componentpoints,stage,pins,out):
    start=time.monotonic();DEST.mkdir(parents=True,exist_ok=True)
    target=DEST/'ordinary_full3_all_own_points_complete_numbers.csv.gz'
    fields=['entity_uid','ordinary_same_place_identity','all_three_own_point_uses','complete_number_count']
    suffixes=SOURCE_FIELDS+POINT_FIELDS+('point_use_raw_flags_json','representative_point_use','historical_measurement_asserted','point_reuse_or_continuity_inference_status','native_codes_as_imported_no_cross_year_backfill')
    for year in YEARS: fields.extend(f'{k}_{year}' for k in suffixes)
    cols=list(ordinary.columns);groups={}
    for values in ordinary.itertuples(index=False,name=None):
        row=dict(zip(cols,values));sid=row['source_record_id']
        if sid in componentpoints: groups.setdefault(row['root'],{})[int(row['census_year'])]=row
    written=0;excluded=[];populations={y:0 for y in YEARS};uids=set()
    with target.open('wb') as raw:
        with gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0,compresslevel=9) as zipped:
            import io
            with io.TextIOWrapper(zipped,encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
                for root,years in sorted(groups.items(),key=lambda item:tuple(item[1].get(y,{}).get('source_record_id','') for y in YEARS)):
                    if set(years)!=set(YEARS):
                        excluded.append({'root':str(root),'reason':'not_three_ordinary_rows','source_ids':[r['source_record_id'] for r in years.values()]});continue
                    ids=[years[y]['source_record_id'] for y in YEARS]
                    bad=[y for y in YEARS if not math.isfinite(float(years[y]['population']))]
                    if bad:
                        excluded.append({'root':str(root),'reason':'unknown_population','unknown_years':bad,'source_ids':ids});continue
                    encoded=json.dumps(ids,ensure_ascii=False,separators=(',',':'))
                    uid='np3:'+base64.urlsafe_b64encode(hashlib.sha256(encoded.encode()).digest()).decode().rstrip('=')
                    assert uid not in uids;uids.add(uid)
                    record={'entity_uid':uid,'ordinary_same_place_identity':True,'all_three_own_point_uses':True,'complete_number_count':3}
                    for year in YEARS:
                        row=years[year];point=state.point_rows[row['source_record_id']]
                        assert math.isfinite(float(point['latitude'])) and math.isfinite(float(point['longitude']))
                        for k in SOURCE_FIELDS: record[f'{k}_{year}']=clean(row.get(k))
                        for k in POINT_FIELDS: record[f'{k}_{year}']=clean(point.get(k))
                        point_raw={k:clean(v) for k,v in point.items() if any(term in k.lower() for term in ['inference','quality','binding','calibration','comparability','historical','asserted'])}
                        record[f'point_use_raw_flags_json_{year}']=json.dumps(point_raw,ensure_ascii=False,separators=(',',':'),default=str)
                        record[f'representative_point_use_{year}']=True
                        record[f'historical_measurement_asserted_{year}']=False
                        classification=' '.join(str(point.get(k,'')) for k in ['coordinate_admission_status','point_origin_kind','admission_rule'])
                        record[f'point_reuse_or_continuity_inference_status_{year}']='explicit_retrospective_inference' if any(x in classification.lower() for x in ['retrospect','continuity','transfer','reuse','inherited']) else 'accepted_use_origin_retained_historical_measurement_unknown'
                        record[f'native_codes_as_imported_no_cross_year_backfill_{year}']=True
                        populations[year]+=int(row['population'])
                    writer.writerow(record);written+=1
    unknown=[r for r in excluded if r['reason']=='unknown_population']
    assert len(unknown)==1 and unknown[0]['unknown_years']==[2010],unknown
    receipt={'working_stage':stage,'file':str(target),'sha256':digest(target),'bytes':target.stat().st_size,'rows':written,'columns':len(fields),'population_by_year':populations,'all_three_own_point_components_before_number_filter':len(groups),'excluded_components':excluded,'unknown_population_never_zero_or_imputed':True,'native_identifiers':'Only selected source row oktmo/okato as imported; empty historical values remain unknown. No chronology or backfill asserted.','entity_uid_recipe':'np3: + unpadded URL-safe base64 of full SHA256 digest of UTF-8 compact JSON ordered [2002 source ID,2010 source ID,2021 source ID]','coordinate_claim':'Every census row has its own admitted representative point use; raw point-use fields retained. Historical measurement and boundary calibration are not asserted.','wall_seconds':round(time.monotonic()-start,3)}
    (out/'export_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (out/'export_source_hash_manifest.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2)+'\n')
    (out/'export_recipe.md').write_text(f'# Ordinary complete-number full3 export\n\nRun `python research_rebuild/evidence/working_full_chain_20261007/build_report.py --stage {stage}` from repository root.\n\nThe gzip CSV lives outside Git at `{target}`. One entity is an ordered tuple of three selected source IDs linked by admitted same-place identity. All three ordinary rows must have admitted own point uses and finite populations; the one unknown 2010 component is excluded in export_receipt.json. Zero is retained as zero. Source names, quality, coordinates and imported native codes remain separate by census year. Empty codes remain unknown. Per-year raw point uses preserve inference claims and origin references.\n\nThe full source manifest and recipe are in Git; the compressed export is not. Gzip metadata and source-ID sort order are deterministic.\n')
    return receipt
