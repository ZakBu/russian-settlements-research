from pathlib import Path
import csv, json, math, re, hashlib, datetime, duckdb

OUT = Path('/workspace/settlements-work/continuation_20261004/root/tenth_point_spread_conflict_diagnostic')
HOLD = Path('/workspace/settlements-work/continuation_20261004/accepted_mass_tenth_reviewed1117/point_continuity_holds.csv')
GRAPH = Path('/workspace/settlements-work/continuation_20261004/accepted_mass_tenth_reviewed1117/accepted_identity_edges.parquet')
POINTS = Path('/workspace/settlements-work/continuation_20261004/accepted_mass_tenth_reviewed1117/accepted_point_uses.parquet')
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EVIDENCE = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet')
DBF_PARSED = Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet')
DBF_RAW = Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
SQL2009 = Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql')
XLS2002 = Path('/workspace/settlements-raw/data/raw/2002/070_48ec6f4a77_Irkut_obl_new.xls')
XLS2010 = Path('/workspace/settlements-raw/data/raw/2010/008_342f3c208b_16._20Сиб_ФО_2010.xls')
TOCHNO = Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def dist(a_lat,a_lon,b_lat,b_lon):
    r=6371.0088; p1=math.radians(a_lat);p2=math.radians(b_lat)
    dp=math.radians(b_lat-a_lat);dl=math.radians(b_lon-a_lon)
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(h))
def dump_csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

holds=list(csv.DictReader(HOLD.open(encoding='utf-8',newline='')))
spread=[r for r in holds if r['hold']=='accepted_point_witness_spread_over_5km']
event=[r for r in holds if r['hold']=='federal_event_or_global_block']
assert len(spread)==36 and len(event)==5 and len(holds)==41
components=[]; ids=[]
for r in spread:
    m=json.loads(r['members_json']);ids.extend(m);components.append((r,m))
ids=list(dict.fromkeys(ids))
con=duckdb.connect()
ph=','.join(['?']*len(ids))
selcols=['source_record_id','census_year','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','latitude','longitude','coordinate_source','source_native_id','okato','oktmo','source_file','source_sheet','source_row','source_locator']
selrows=con.execute(f"select {','.join(selcols)} from read_parquet('{SELECTED}') where source_record_id in ({ph})",ids).fetchall()
S={r[0]:dict(zip(selcols,r)) for r in selrows}
pcols=['target_source_record_id','target_year','latitude','longitude','coordinate_source','coordinate_provider','coordinate_provider_id','admission_rule','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','source_name','source_type','source_region','source_okato_raw','source_oktmo_raw','coordinate_provenance','coordinate_admission_status']
prows=con.execute(f"select {','.join(pcols)} from read_parquet('{POINTS}') where target_source_record_id in ({ph})",ids).fetchall()
P={}
for r in prows: P.setdefault(r[0],[]).append(dict(zip(pcols,r)))
ranked=[]
for r,m in components:
    cur=next((S[x] for x in m if x in S and int(S[x]['census_year'])==2021),None)
    if cur is not None: ranked.append((float(cur['population'] or 0),r,m,cur))
ranked.sort(key=lambda x:x[0],reverse=True)

top=[]
for rank,(pop,r,m,cur) in enumerate(ranked[:10],1):
    oldids=[x for x in m if x in S and int(S[x]['census_year'])<2021]
    oldpoints=[q for x in m for q in P.get(x,[]) if str(q['target_year']).replace('.0','') in ('2002','2010')]
    curpoints=[q for x in m for q in P.get(x,[]) if str(q['target_year']).replace('.0','')=='2021']
    op=oldpoints[0] if oldpoints else None
    cp=curpoints[0] if curpoints else None
    dbf=None
    if op:
        match=re.search(r'(?:raw_dbf_record_number_1based|DBF_record_1based)=(\d+)',str(op['point_origin_locator']))
        if match:
            d=con.execute(f"select record_number_1based,record_byte_offset_0based,historical_okato,ter_raw_text,kod1_raw_text,kod2_raw_text,kod3_raw_text,name_raw,scokato_raw_text,settlement_type_raw,latitude_from_lat,longitude_from_long from read_parquet('{DBF_PARSED}') where record_number_1based=?",[int(match.group(1))]).fetchone()
            if d: dbf=dict(zip(['record_number_1based','record_byte_offset_0based','historical_okato','ter','kod1','kod2','kod3','name_raw','scokato_raw','type_raw','lat','lon'],d))
    old_context=[S[x] for x in oldids]
    old_admin=' | '.join(f"{z['census_year']}:{z['region_raw']} / {z['district_raw']} / {z['municipality_raw']}" for z in old_context)
    cp_lat=cp['latitude'] if cp else cur['latitude']; cp_lon=cp['longitude'] if cp else cur['longitude']
    op_lat=op['latitude'] if op else None; op_lon=op['longitude'] if op else None
    top.append({
        'rank_by_current_population':rank,'current_population_context_only':pop,'target_name':cur['settlement_name'],'target_type':cur['settlement_type'],
        'accepted_point_witness_component_spread_km':float(r['spread_km']),'members_json':r['members_json'],
        'old_source_contexts':old_admin,'old_point_target_id':op['target_source_record_id'] if op else '',
        'old_point_lat':op_lat,'old_point_lon':op_lon,'old_point_origin_kind':op['point_origin_kind'] if op else '',
        'old_point_origin_locator':op['point_origin_locator'] if op else '', 'old_point_origin_sha256':op['point_origin_sha256'] if op else '',
        'old_point_raw_dbf_code':dbf['historical_okato'] if dbf else '', 'old_point_raw_dbf_name':dbf['name_raw'] if dbf else '',
        'old_point_raw_dbf_type':dbf['type_raw'] if dbf else '', 'old_point_raw_dbf_record':dbf['record_number_1based'] if dbf else '',
        'old_point_raw_dbf_byte_offset':dbf['record_byte_offset_0based'] if dbf else '',
        'old_point_distance_to_current_accepted_point_km':round(dist(op_lat,op_lon,cp_lat,cp_lon),6) if op and cp and op_lat is not None and cp_lat is not None else '',
        'current_selected_source_record_id':cur['source_record_id'],'current_selected_region':cur['region_raw'],'current_selected_district':cur['district_raw'],
        'current_selected_municipality':cur['municipality_raw'],'current_native_id_raw':cur['source_native_id'],'current_okato_raw':cur['okato'],'current_oktmo_raw':cur['oktmo'],
        'current_raw_selected_lat':cur['latitude'],'current_raw_selected_lon':cur['longitude'],'current_raw_coordinate_source':cur['coordinate_source'],
        'current_accepted_point_lat':cp_lat,'current_accepted_point_lon':cp_lon,'current_accepted_point_provider':cp['coordinate_provider'] if cp else '',
        'current_accepted_point_provider_id':cp['coordinate_provider_id'] if cp else '', 'current_point_admission_rule':cp['admission_rule'] if cp else '',
        'diagnostic_disposition':'hold preserved; conflict is between distinct historical DBF point witness and current accepted point; no independent raw source re-review or quarantine proposed by this top-10 screen'
    })
TOP=OUT/'top10_spread_conflicts.csv'
dump_csv(TOP,top,list(top[0]))

# Keep the five existing event/global blocks visible without attempting to reinterpret them.
evids=[r['target_source_record_id'] for r in event]
evcols=['source_record_id','census_year','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','source_file','source_sheet','source_row']
evrows=con.execute(f"select {','.join(evcols)} from read_parquet('{SELECTED}') where source_record_id in ({','.join(['?']*len(evids))})",evids).fetchall()
EV={r[0]:dict(zip(evcols,r)) for r in evrows}
events=[]
for r in event:
    z=EV.get(r['target_source_record_id'],{})
    events.append({'source_record_id':r['target_source_record_id'],'hold':r['hold'],'name':z.get('settlement_name'),'type':z.get('settlement_type'),'region':z.get('region_raw'),'district':z.get('district_raw'),'population_context_only':z.get('population'),'source_file':z.get('source_file'),'source_sheet':z.get('source_sheet'),'source_row':z.get('source_row'),'disposition':'hard hold preserved; no reinterpretation attempted'})
EVOUT=OUT/'five_event_global_holds.csv';dump_csv(EVOUT,events,list(events[0]))

# Exact bounded Taezhny case: old Shelekhovsky source versus separate current Nizhneudinsky tract.
TAE_2002='2002:070_48ec6f4a77_Irkut_obl_new.xls:Sheet1:1623'
TAE_2010='2010:008_342f3c208b_16._20Сиб_ФО_2010.xls:Sib:4924'
TAE_CURRENT='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:25538'
NIZ_CURRENT='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:24744'
ta_ids=[TAE_2002,TAE_2010,TAE_CURRENT,NIZ_CURRENT]
trow=con.execute(f"select {','.join(selcols)} from read_parquet('{SELECTED}') where source_record_id in ({','.join(['?']*len(ta_ids))})",ta_ids).fetchall()
T={r[0]:dict(zip(selcols,r)) for r in trow}
evrows=con.execute(f"select source_record_id,source_evidence_json from read_parquet('{EVIDENCE}') where source_record_id in ({','.join(['?']*len(ta_ids))})",ta_ids).fetchall()
TE={r[0]:json.loads(r[1]) for r in evrows}
tp=con.execute(f"select target_source_record_id,target_year,latitude,longitude,coordinate_source,coordinate_provider,coordinate_provider_id,admission_rule,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind,source_name,source_type,source_region,source_okato_raw,source_oktmo_raw,coordinate_provenance,coordinate_admission_status from read_parquet('{POINTS}') where target_source_record_id in ({','.join(['?']*len(ta_ids))})",ta_ids).fetchall()
TP={}
for rr in tp:TP.setdefault(rr[0],[]).append(dict(zip(pcols,rr)))
# pinned exact DBF original record and code parent context
old_dbf=con.execute(f"select record_number_1based,record_byte_offset_0based,historical_okato,ter_raw_text,kod1_raw_text,kod2_raw_text,kod3_raw_text,name_raw,scokato_raw_text,settlement_type_raw,latitude_from_lat,longitude_from_long from read_parquet('{DBF_PARSED}') where record_number_1based=38578").fetchone()
# Exact old classifier line and parent tree lines
sql_lines=SQL2009.read_text(encoding='utf-8',errors='replace').splitlines()
old_code_lines=[(i+1,x) for i,x in enumerate(sql_lines) if x.startswith('25255553005\t')]
parent_lines=[(i+1,x) for i,x in enumerate(sql_lines) if x.startswith(('25255000\t','25255550\t','25255553\t','25255553000\t'))]
# Count classifier native settlement rows with exact normalized object label/type using literal SQL data.
# Exact line counts are raw tab-delimited records (administrative parent labels remain separate).
# Current native code frequencies in the frozen selected population layer.
code_counts=con.execute(f"select count(*) from read_parquet('{SELECTED}') where census_year=2021 and source_native_id=?",[T[TAE_CURRENT]['source_native_id']]).fetchone()[0]
same_region_rows=con.execute(f"select source_record_id,settlement_name,settlement_type,region_raw,district_raw,municipality_raw,population,latitude,longitude,source_native_id,okato,oktmo from read_parquet('{SELECTED}') where census_year=2021 and lower(settlement_name) in ('таежный','таёжный') and lower(region_raw) like '%иркут%' order by source_record_id").fetchall()
same_region_fields=['source_record_id','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','latitude','longitude','source_native_id','okato','oktmo']
same_region_output=[dict(zip(same_region_fields,x)) for x in same_region_rows]
same_region_csv=OUT/'taezhny_current_irkutsk_name_collision_context.csv'
dump_csv(same_region_csv,same_region_output,same_region_fields)
point_old_2002=TP.get(TAE_2002,[{}])[0];point_old_2010=TP.get(TAE_2010,[{}])[0]
point_shelekhov=TP.get(TAE_CURRENT,[{}])[0];point_niz=TP.get(NIZ_CURRENT,[{}])[0]
# graph links explicitly measured for exact target records
edge_counts={}
for name,x in [('old_2002',TAE_2002),('old_2010',TAE_2010),('current_shelekhov',TAE_CURRENT),('current_nizhneudinsky',NIZ_CURRENT)]:
    edge_counts[name]=con.execute(f"select count(*) from read_parquet('{GRAPH}') where from_source_record_id=? or to_source_record_id=?",[x,x]).fetchone()[0]
# pairwise distances point comparisons
old_xy=(point_old_2010['latitude'],point_old_2010['longitude'])
cur_sh_xy=(point_shelekhov['latitude'],point_shelekhov['longitude'])
cur_niz_xy=(point_niz['latitude'],point_niz['longitude'])
wd_niz=None
for q in TP.get(NIZ_CURRENT,[]):
    if q.get('coordinate_provider')=='Wikidata': wd_niz=q;break
if not wd_niz: raise RuntimeError('expected accepted current WD witness for Nizhneudinsky tract missing')

tae={
 'status':'finite_source_conflict_diagnostic_no_canonical_mutation',
 'reviewed_at_utc':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
 'source_observations':{
  'old_2002':{**T[TAE_2002],'raw_workbook_sha256':sha(XLS2002),'raw_sheet_row_1based':1623,'raw_workbook_values':['1623','посёлок Таежный','0'],'parent_heading':'Шелеховский район - все сельское население; Сельские населенные пункты, подчиненные администрации пгт Большой Луг','source_evidence_flags':{k:TE[TAE_2002].get(k) for k in ['legacy_identity_conflict','legacy_identity_reasons','legacy_identity_status','legacy_matched_to_source_record_id','legacy_verified_successor_settlement_id','legacy_same_year_collision','is_federal_aggregate','is_additive_settlement_record']}},
  'old_2010':{**T[TAE_2010],'raw_workbook_sha256':sha(XLS2010),'raw_sheet_row_1based':4924,'raw_workbook_values':['4918','Иркутская область','п. Таежный','0'],'row_district_cell_blank':True,'prior_sheet_context_row_4920':'Иркутская область | Шелеховский район | пгт Большой Луг','source_evidence_flags':{k:TE[TAE_2010].get(k) for k in ['legacy_identity_conflict','legacy_identity_reasons','legacy_identity_status','legacy_matched_to_source_record_id','legacy_verified_successor_settlement_id','legacy_same_year_collision','is_federal_aggregate','is_additive_settlement_record']}},
  'current_shelekhovsky':{**T[TAE_CURRENT],'selected_source_sha256':sha(TOCHNO),'selected_row_1based':25538,'current_raw_point_is_source_row_point':True,'native_OKTMO_frequency_selected_2021':code_counts,'current_same_name_rows_in_Irkutsk_region':len(same_region_output),'same_name_collision_context_csv':str(same_region_csv),'accepted_point_use':point_shelekhov},
  'separate_current_nizhneudinsky':{**T[NIZ_CURRENT],'selected_source_sha256':sha(TOCHNO),'selected_row_1based':24744,'accepted_point_use':point_niz,'independent_Wikidata_P625_witness':wd_niz},
 },
 'historical_2009_classifier':{'matching_native_row':old_code_lines,'parent_rows':parent_lines,'raw_code':'25255553005','parent_classification':'Shelekhovsky district / settlements subordinate to urban-type settlement Bolshoy Lug'},
 'historical_2011_dbf':{'source_sha256':sha(DBF_RAW),'parsed_row':dict(zip(['record_number_1based','byte_offset_0based','raw_OKATO','TER','KOD1','KOD2','KOD3','raw_name','raw_SCOKATO','raw_type','latitude','longitude'],old_dbf)),'source_code_matches_Shelekhovsky_classifier':True,'coordinate_warning':'Raw point is 522.208508 km from current Shelekhovsky settlement row and 0.064976 km from the distinct Nizhneudinsky Taezhny tract. Keep raw source code/name/type and raw coordinates, but quarantine these point uses from physical point selection.'},
 'spatial_comparisons_km':{'2011_DBF_old_point_to_current_Shelekhovsky_row25538':round(dist(old_xy[0],old_xy[1],cur_sh_xy[0],cur_sh_xy[1]),6),'2011_DBF_old_point_to_current_Nizhneudinsky_tract_row24744':round(dist(old_xy[0],old_xy[1],cur_niz_xy[0],cur_niz_xy[1]),6),'2011_DBF_old_point_to_Wikidata_Q4479322_Nizhneudinsky_tract':round(dist(old_xy[0],old_xy[1],wd_niz['latitude'],wd_niz['longitude']),6),'current_Shelekhovsky_row25538_direct_point_to_Nizhneudinsky_row24744_direct_point':round(dist(cur_sh_xy[0],cur_sh_xy[1],cur_niz_xy[0],cur_niz_xy[1]),6)},
 'graph_readback':{'tenth_graph_sha256':sha(GRAPH),'exact_incident_edge_counts':edge_counts,'note':'No accepted identity-edge row has either old Shelekhovsky endpoint or either current 2021 endpoint. Therefore this audit cannot say an accepted graph edge is wrong or corrected; it proposes a finite raw-point quarantine only. The old source rows and current Shelekhovsky row are a candidate continuity route for separate independent identity review if parent elects it.'},
 'point_use_proposal':[
  {'target_source_record_id':TAE_2002,'old_point_origin_dbf_record':38578,'old_point_origin_sha256':sha(DBF_RAW),'proposed_action':'quarantine this point use from accepted spatial continuity; retain raw evidence and the 2002 observation unchanged'},
  {'target_source_record_id':TAE_2010,'old_point_origin_dbf_record':38578,'old_point_origin_sha256':sha(DBF_RAW),'proposed_action':'quarantine this point use from accepted spatial continuity; retain raw evidence and the 2010 observation unchanged'},
 ],
 'point_preservation':{'current_shelekhovsky_row25538':'keep its current native-source representative point 51.9963239,103.9944876 pending no contrary current-source evidence; it is a separate physical source row with source-native OKTMO 25655404121, unique in selected 2021.', 'current_nizhneudinsky_row24744':'keep its current native-source and Wikidata points 55.6551411,98.9965108 and 55.653889,98.996667 respectively; same current source ID is a distinct `участок` in Nizhneudinsky district, raw native OKTMO 25628422116. Do not merge it with Shelekhovsky settlement from coordinate coincidence.'},
 'limits':['No identity edge or point use was added, removed, or changed.','The old point row uses the right raw classifier code/name/type for the Shelekhovsky source; the factual defect is the coordinate’s severe conflict with the old source’s parent context and its spatial coincidence with a distinct Nizhneudinsky record.','No historical coordinate measurement, boundary, code validity, or population equivalence is asserted.','Legacy old records retain their existing administrative_conflict flags; this diagnostic does not resolve them.','This is a bounded targeted finding, not a root-cause audit of all DBF coordinates.'],
}
TAEOUT=OUT/'taezhny_oldpoint_binding_audit.json';TAEOUT.write_text(json.dumps(tae,ensure_ascii=False,indent=2)+'\n')
# Manifest and source pins; files are frozen inputs, only this own output directory was written.
inputs=[HOLD,GRAPH,POINTS,SELECTED,EVIDENCE,DBF_PARSED,DBF_RAW,SQL2009,XLS2002,XLS2010,TOCHNO]
receipt={'status':'read_only_diagnostic_complete_no_canonical_changes','reviewed_at_utc':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
 'baseline':{'graph':{'path':str(GRAPH),'sha256':sha(GRAPH),'rows':348281},'points':{'path':str(POINTS),'sha256':sha(POINTS),'rows':415744},'point_continuity_holds':{'path':str(HOLD),'sha256':sha(HOLD),'rows':41,'spread_over_5km':36,'event_or_global_block':5},'selected':{'path':str(SELECTED),'sha256':sha(SELECTED)},'source_evidence':{'path':str(EVIDENCE),'sha256':sha(EVIDENCE)}},
 'inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in inputs},
 'outputs':{TOP.name:{'sha256':sha(TOP),'rows':len(top)},EVOUT.name:{'sha256':sha(EVOUT),'rows':len(events)},TAEOUT.name:{'sha256':sha(TAEOUT)},same_region_csv.name:{'sha256':sha(same_region_csv),'rows':len(same_region_output)},'build_diagnostic.py':{'sha256':sha(OUT/'build_diagnostic.py')}},
 'findings':{'top10_ranked_by_current_population':[{'rank':r['rank_by_current_population'],'name':r['target_name'],'population_context_only':r['current_population_context_only'],'spread_km':r['accepted_point_witness_component_spread_km']} for r in top],
 'taezhny_point_uses_flagged_for_quarantine_only':[TAE_2002,TAE_2010],'current_points_preserved':[TAE_CURRENT,NIZ_CURRENT]},
 'execution':'narrow DuckDB column projections, raw XLS rows reopened with xlrd, native DBF row verified against the local parsed raw-row index and source-byte pin; no full national scans and no output written outside this folder.'}
RCPT=OUT/'receipt.json';RCPT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print('TOP10',TOP,sha(TOP),len(top))
print('EVENTS',EVOUT,sha(EVOUT),len(events))
print('TAEZHNY',TAEOUT,sha(TAEOUT))
print('RECEIPT',RCPT,sha(RCPT))
