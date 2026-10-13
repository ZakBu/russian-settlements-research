#!/usr/bin/env python3
"""Stage mass-safe temporal candidates from extant Rosstat comparisons and exact keys.

This is a candidate-generation/audit script only. It never changes accepted ledgers.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

ROOT = Path('/workspace')
OUT = ROOT / 'settlements-work/continuation_20261004/root/R4/temporal_mass/primary_comparison_extension/review_freeze_v3'
SELECTED = ROOT / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
SOURCE_EVIDENCE = ROOT / 'settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet'
POINTS = ROOT / 'settlements-work/continuation_20261004/accepted_mass_batch/accepted_point_uses.parquet'
EDGES = ROOT / 'settlements-work/continuation_20261004/accepted_mass_batch/accepted_identity_edges.parquet'
RESIDUAL = ROOT / 'settlements-work/continuation_20261004/accepted_mass_batch/joint_residual.parquet'
TABLE49 = ROOT / 'settlements-data/research_rebuild/evidence/discovery/yearbook_table49_2010_2021_candidates_r2_20260930/bridge_candidates_2010_2021.csv'
TABLE49_PDF_SHA = 'bac43b438869d7b11ca595acd121726833d2bf2e54004351db825cade4c29da7'
CLASSIFIER = ROOT / 'settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet'
GEOKLADR = ROOT / 'settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet'

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def write_csv(path: Path, rows: list[dict], fields: list[str], *, strict: bool = False) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='raise' if strict else 'ignore')
        w.writeheader()
        for row in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v) for k,v in row.items()})

class UF:
    def __init__(self): self.p={}; self.years={}
    def find(self,x):
        if x not in self.p: self.p[x]=x; self.years[x]={year(x)}
        if self.p[x]!=x: self.p[x]=self.find(self.p[x])
        return self.p[x]
    def union(self,a,b):
        a,b=self.find(a),self.find(b)
        if a==b: return True
        if self.years[a]&self.years[b]: return False
        self.p[b]=a; self.years[a]|=self.years.pop(b)
        return True
    def connected(self,a,b): return self.find(a)==self.find(b)
    def component_years(self,x): return sorted(self.years[self.find(x)])

def path_is_safe(uf: UF, edges: list[tuple[str,str,int,int]]) -> bool:
    """Test a small candidate path against the accepted graph without copying it."""
    parent={}; years_by_root={}
    def find(x):
        if x not in parent:
            root=uf.find(x); parent[x]=root
            years_by_root.setdefault(root,set(uf.years[root]))
        if parent[x]!=x and parent[x] in parent: parent[x]=find(parent[x])
        return parent[x]
    # Use synthetic local roots for touched existing components.
    for a,b,_,_ in edges:
        find(a); find(b)
    root_parent={x:x for x in years_by_root}
    def rf(x):
        if root_parent[x]!=x: root_parent[x]=rf(root_parent[x])
        return root_parent[x]
    root_years={x:set(y) for x,y in years_by_root.items()}
    for a,b,_,_ in edges:
        ra,rb=rf(parent[a]),rf(parent[b])
        if ra==rb: continue
        if root_years[ra] & root_years[rb]: return False
        root_parent[rb]=ra; root_years[ra]|=root_years.pop(rb)
    return True

def year(x):
    try: return int(str(x)[:4])
    except Exception: return -1

def hav(lat1,lon1,lat2,lon2):
    rad=math.pi/180
    p1,p2=lat1*rad,lat2*rad
    dp=(lat2-lat1)*rad; dl=(lon2-lon1)*rad
    z=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371.0088*2*math.asin(min(1,math.sqrt(z)))

def norm_source_name(x):
    s=str(x or '').strip().lower().replace('ё','е')
    return re.sub(r'^(?:город|г\.?|село|с\.?|пгт|пос[её]лок|д\.?|деревня|аул|станица|ст-ца)\s+','',s).strip()

def classifier_type(s):
    s=str(s or '').lower().replace('ё','е').strip()
    return {'поселок городского типа':'пгт','город':'город','село':'село','деревня':'деревня',
            'поселок сельского типа':'посёлок','поселок':'посёлок'}.get(s)

def main():
    if (OUT/'freeze_manifest.json').exists():
        raise SystemExit(f'refusing to overwrite frozen candidate package: {OUT}')
    OUT.mkdir(parents=True, exist_ok=True)
    con=duckdb.connect()
    # All source endpoints are selected observations. Current-year primary 2010 urban
    # residuals are the prioritization set; source_evidence remains historical context.
    selected=con.execute(f"select * from read_parquet('{SELECTED}')").fetchdf()
    residual=con.execute(f"select * from read_parquet('{RESIDUAL}') where census_year=2010 and settlement_type in ('город','пгт') and (population_value_quality like 'reviewed_primary%' or population_value_quality='direct_official_city_value')").fetchdf()
    evidence={r[0]:json.loads(r[1]) for r in con.execute(f"select source_record_id,source_evidence_json from read_parquet('{SOURCE_EVIDENCE}')").fetchall()}
    # Accepted point uses only; require actual historical typed coordinate + current
    # physical provider point. Retrospective/inferred reuse is deliberately excluded.
    point_rows=con.execute(f"""select target_source_record_id,target_year,latitude,longitude,point_origin_kind,
       coordinate_source,coordinate_admission_status,coordinate_application_family,
       point_origin_file,point_origin_sha256,point_origin_locator,source_name,source_type,source_region,
       source_sha256,source_locator,admission_allowed,lineage_event_roles_json
       from read_parquet('{POINTS}')""").fetchdf().to_dict('records')
    pidx=defaultdict(list)
    for p in point_rows: pidx[p['target_source_record_id']].append(p)
    # Cached 2009 classification and 2011 named typed geocoding objects. These are
    # read-only witnesses, not population sources and not census endpoint selectors.
    class_rows=con.execute(f"select historical_okato,name,status,is_settlement_raw,source_line_1based,source_sha256 from read_parquet('{CLASSIFIER}')").fetchall()
    classifier_by_name=defaultdict(list)
    for code,name,status,is_np,line,csha in class_rows:
        if name:
            classifier_by_name[norm_source_name(name)].append({'code':str(code),'name':name,'status':status,'type':classifier_type(status),
                'is_settlement_raw':str(is_np).lower() in ('t','true','1'),'line':line,'sha256':csha})
    geo_rows=con.execute(f"select historical_okato,name_raw,settlement_type_raw,longitude_from_long,latitude_from_lat,record_number_1based,record_byte_offset_0based,is_deleted,source_sha256 from read_parquet('{GEOKLADR}')").fetchall()
    geo_by_code=defaultdict(list)
    for code,name,typ,lon,lat,row,offset,deleted,gsha in geo_rows:
        if not deleted and lon is not None and lat is not None:
            geo_by_code[str(code)].append({'code':str(code),'name':name,'type':typ,'longitude':lon,'latitude':lat,'row':row,'byte_offset':offset,'sha256':gsha})
    accepted=con.execute(f"select from_source_record_id,to_source_record_id from read_parquet('{EDGES}') where relation='same_place' and decision_status like '%accepted%'").fetchall()
    uf=UF()
    for a,b in accepted: uf.union(a,b)
    # Source selected rows indexed by exact name-region key. No fuzzy name path.
    row_by_id={r.source_record_id:r for r in selected.itertuples(index=False)}
    keyed=defaultdict(lambda:defaultdict(list))
    for r in selected.itertuples(index=False):
        nm=getattr(r,'name_norm',None); rg=getattr(r,'region_norm',None)
        if nm and rg and getattr(r,'is_additive_settlement_record',True) is not False:
            keyed[(nm,rg)][int(r.census_year)].append(r)
    out=[]; holds=[]; proposals=[]
    # Candidate family A: primary 2010 row and exact unique 2002/2021 counterparts,
    # with independently accepted physical points no farther than 5 km. This permits
    # only ordinary same-name regional continuity; type changes are explicit in output.
    for r in residual.itertuples(index=False):
        se=evidence.get(r.source_record_id,{})
        key=(r.name_norm,r.region_norm)
        matches=keyed.get(key,{})
        old=matches.get(2002,[]); modern=matches.get(2021,[])
        inv={
            'source_record_id':r.source_record_id,'census_year':2010,'settlement_name':r.settlement_name,
            'settlement_type':r.settlement_type,'region_raw':r.region_raw,'district_raw':r.district_raw,
            'population':r.population,'population_quality':r.population_value_quality,
            'source_selection_component':r.source_selection_component,'source_sha256':r.source_sha256,
            'source_locator':r.source_locator,'population_scope':r.population_scope,
            'entity_grain_status':r.entity_grain_status,'is_additive_settlement_record':r.is_additive_settlement_record,
            'legacy_source_evidence':se,'key_2002_count':len(old),'key_2021_count':len(modern),
            'current_primary_context_supersedes_legacy_flag':bool(se.get('legacy_identity_conflict') and 'publication_binding' in str(se.get('legacy_quality_join_status',''))),
        }
        if bool(se.get('is_federal_aggregate',False)) or se.get('grain_review_flag')=='federal_aggregate_hard_block':
            inv['stage_status']='hold_federal_aggregate_hard_block'
            inv['hold_reason']='authoritative current source_evidence federal-aggregate hard block'
            holds.append(inv); out.append(inv); continue
        if len(old)==1 and len(modern)==1:
            o,m=old[0],modern[0]
            op=[p for p in pidx.get(o.source_record_id,[]) if p['coordinate_admission_status'] and 'accepted' in str(p['coordinate_admission_status']) and p['point_origin_kind'] in ('geokladr_2011_raw_dbf_coordinate','raw_named_typed_geo2011_object')]
            mp=[p for p in pidx.get(m.source_record_id,[]) if p['coordinate_admission_status'] and 'accepted' in str(p['coordinate_admission_status']) and p['point_origin_kind'] in ('tochno_2021_dadata_raw_parquet_point','raw_2021_own_provider_named_point','geonames_ru_txt_named_place_point','wikidata_P625_point_claim','wikidata_truthy_p625_raw_claim')]
            pairs=[]
            for a in op:
                for b in mp:
                    d=hav(float(a['latitude']),float(a['longitude']),float(b['latitude']),float(b['longitude']))
                    if d<=5: pairs.append((d,a,b))
            inv.update({'historical_endpoint_id':o.source_record_id,'historical_name':o.settlement_name,'historical_type':o.settlement_type,
                'modern_endpoint_id':m.source_record_id,'modern_name':m.settlement_name,'modern_type':m.settlement_type,
                'accepted_historical_point_count':len(op),'accepted_modern_physical_point_count':len(mp),
                'best_direct_point_distance_km':min((p[0] for p in pairs),default=None)})
            # A type/status-change route requires a nonmunicipal 2009 classifier row
            # for the exact name, code-region prefix, and matching historical type,
            # plus the same named typed GeoKLADR object and a direct accepted 2021
            # physical point within 5 km. Status transition remains an interval event.
            typechange=(o.settlement_type!=r.settlement_type or m.settlement_type!=r.settlement_type)
            class_support=None
            if typechange and len(str(getattr(m,'okato','') or ''))>=2:
                opts=[q for q in classifier_by_name.get(norm_source_name(r.settlement_name),[])
                      if q['code'][:2]==str(m.okato)[:2] and
                         ((q['is_settlement_raw'] and q['type'] in (o.settlement_type,r.settlement_type)) or
                          (not q['is_settlement_raw'] and not q['type'] and r.settlement_type==m.settlement_type=='город'))]
                if len(opts)==1:
                    q=opts[0]
                    hist_geo=[]
                    for code,objects in geo_by_code.items():
                        if code.startswith(q['code']):
                            for g in objects:
                                if norm_source_name(g['name'])==norm_source_name(q['name']) and str(g['type']).lower() in ({'город':'г','пгт':'пгт','село':'с','деревня':'д','посёлок':'п'}[t] for t in (o.settlement_type,r.settlement_type,m.settlement_type)):
                                    hist_geo.append(g)
                    g_pairs=[]
                    for g in hist_geo:
                        for p in mp:
                            d=hav(float(g['latitude']),float(g['longitude']),float(p['latitude']),float(p['longitude']))
                            if d<=5: g_pairs.append((d,g,p))
                    if len(hist_geo)==1 and g_pairs:
                        d,g,p=min(g_pairs,key=lambda x:x[0])
                        class_support={'classifier_2009_code':q['code'],'classifier_status':q['status'],'classifier_type':q['type'],
                           'classifier_source_file':str(CLASSIFIER),'classifier_is_settlement_raw':q['is_settlement_raw'],'classifier_status_field_raw':q['status'],'classifier_line_1based':q['line'],'classifier_sha256':q['sha256'],
                           'geokladr_2011_code':g['code'],'geokladr_name':g['name'],'geokladr_type':g['type'],
                           'geokladr_source_file':str(GEOKLADR),'geokladr_record_number_1based':g['row'],'geokladr_byte_offset_0based':g['byte_offset'],'geokladr_sha256':g['sha256'],
                           'geokladr_latitude':g['latitude'],'geokladr_longitude':g['longitude'],
                           'modern_physical_point':{k:p.get(k) for k in ('point_origin_kind','point_origin_file','point_origin_sha256','point_origin_locator','latitude','longitude','coordinate_admission_status','lineage_event_roles_json')},
                           'distance_km':round(d,4)}
            if class_support:
                inv['classifier_status_change_support']=class_support
            modern_event_point=(min(pairs,key=lambda x:x[0])[2] if pairs else (class_support or {}).get('modern_physical_point',{}))
            event_json=modern_event_point.get('lineage_event_roles_json')
            explicit_roles=[]
            if event_json:
                try: explicit_roles=json.loads(event_json) if isinstance(event_json,str) else list(event_json)
                except Exception: explicit_roles=[{'unparsed_event_roles_json':str(event_json)}]
            inv['explicit_event_roles_on_modern_point_record']=explicit_roles
            if explicit_roles:
                inv['stage_status']='hold_explicit_event_roles'
                holds.append({**inv,'hold_reason':'explicit source lineage event roles require event-specific identity review'})
            elif (pairs or class_support) and r.is_additive_settlement_record and o.is_additive_settlement_record and m.is_additive_settlement_record and (not typechange or class_support):
                d,p2,p21=min(pairs,key=lambda x:x[0]) if pairs else (class_support['distance_km'],None,None)
                inv['type_change_observed']=typechange
                inv['current_primary_district']=r.district_raw
                # Candidate pair path gets two edges, only if the already-accepted graph
                # does not create a duplicate-year component and no exact pair exists.
                edge_specs=[(o.source_record_id,r.source_record_id,2002,2010),(r.source_record_id,m.source_record_id,2010,2021)]
                if not path_is_safe(uf,edge_specs):
                    inv['stage_status']='hold_graph_year_collision'
                    holds.append({**inv,'hold_reason':'adding adjacent-year path would place duplicate census year in a component'})
                elif [e for e in edge_specs if not uf.connected(e[0],e[1])]:
                    inv['stage_status']='candidate_staged'
                    inv['candidate_family']='exact_unique_name_region_plus_accepted_crossyear_points_and_classifier_status' if typechange else 'exact_unique_name_region_plus_accepted_crossyear_points'
                    inv['assumption']='stable physical settlement identity across census years; exact normalized name and region are unique in each year; independent named typed historical point and accepted modern physical point agree within 5 km; 2009 classifier establishes the observed nonmunicipal status at its date' if typechange else 'stable settlement identity across census years; same normalized name and region is unique in each year; independent direct historical and modern physical points agree within 5 km; no geographic/population harmonization is asserted'
                    inv['evidence_point_2002']=({k:p2.get(k) for k in ('point_origin_kind','point_origin_file','point_origin_sha256','point_origin_locator','latitude','longitude','coordinate_admission_status')} if p2 else {'point_origin_kind':'raw_named_typed_geo2011_object','point_origin_file':str(GEOKLADR),'point_origin_sha256':class_support['geokladr_sha256'],'point_origin_locator':f"record_number_1based={class_support['geokladr_record_number_1based']};byte_offset_0based={class_support['geokladr_byte_offset_0based']}",'latitude':class_support['geokladr_latitude'],'longitude':class_support['geokladr_longitude'],'coordinate_admission_status':'raw_source_direct_exact_named_typed_object'})
                    inv['evidence_point_2021']={k:p21.get(k) for k in ('point_origin_kind','point_origin_file','point_origin_sha256','point_origin_locator','latitude','longitude','coordinate_admission_status')} if p21 else class_support['modern_physical_point']
                    event_start,event_end=((2002,2010) if o.settlement_type!=r.settlement_type else (2010,2021))
                    inv['observed_status_change_event']={'event_type':'settlement_status_changed','observed_interval_start_year':event_start,'observed_interval_end_year':event_end,'observed_types':[o.settlement_type,r.settlement_type,m.settlement_type],'exact_change_date':'unknown'} if typechange else None
                    for a,b,ya,yb in edge_specs:
                        if uf.connected(a,b): continue
                        proposals.append({'edge_id':f'PCE-{hashlib.sha256((a+"|"+b).encode()).hexdigest()[:20]}','relation':'same_place','from_source_record_id':a,'from_year':ya,'to_source_record_id':b,'to_year':yb,
                            'candidate_status':'candidate_for_independent_review','candidate_rule':inv['candidate_family'],'candidate_basis':inv['assumption'],
                            'supporting_key':{'name_norm':r.name_norm,'region_norm':r.region_norm,'unique_selected_endpoints_each_year':True},
                            'row_2002':{'source_record_id':o.source_record_id,'source_sha256':o.source_sha256,'source_locator':o.source_locator,'population':o.population,'name':o.settlement_name,'type':o.settlement_type,'region':o.region_raw,'district':o.district_raw},
                            'row_2010':{'source_record_id':r.source_record_id,'source_sha256':r.source_sha256,'source_locator':r.source_locator,'population':r.population,'name':r.settlement_name,'type':r.settlement_type,'region':r.region_raw,'district':r.district_raw},
                            'row_2021':{'source_record_id':m.source_record_id,'source_sha256':m.source_sha256,'source_locator':m.source_locator,'population':m.population,'name':m.settlement_name,'type':m.settlement_type,'region':m.region_raw,'district':m.district_raw},
                            'point_distance_km':round(d,4),'point_2002_origin':inv['evidence_point_2002'],'point_2021_origin':inv['evidence_point_2021'],
                            'classifier_status_change_support':class_support,'observed_status_change_event':inv['observed_status_change_event'],
                            'legacy_flags_are_not_physical_conflicts':bool(se.get('legacy_identity_conflict',False)),'legacy_source_evidence':se,
                            'population_gain_candidate':r.population,'population_gain_scope':'one 2010 selected primary row, once per component; not an admission or change to population'})
                    # Reserve only for deterministic proposal-union safety among this batch.
                    uf.union(o.source_record_id,r.source_record_id); uf.union(r.source_record_id,m.source_record_id)
                else:
                    inv['stage_status']='hold_already_connected_or_partial'
                    holds.append({**inv,'hold_reason':'at least one exact-key endpoint pair is already connected in accepted graph'})
            elif (o.settlement_type==r.settlement_type==m.settlement_type and
                  all(bool(getattr(x,'is_additive_settlement_record',True)) for x in (o,r,m)) and
                  str(r.region_norm).strip() not in ('москва','санкт петербург') and
                  not bool(se.get('is_federal_aggregate',False))):
                # Lower-strength, still multi-field exact rule: all three selected
                # endpoints share unique full name+region key and exact settlement
                # type; current primary 2010 source is an atomic row. No point is
                # invented or copied. It is staged only as an identity review edge.
                specs=[(o.source_record_id,r.source_record_id,2002,2010),(r.source_record_id,m.source_record_id,2010,2021)]
                good=True
                good=path_is_safe(uf,specs)
                missing=[e for e in specs if not uf.connected(e[0],e[1])]
                if not missing:
                    inv['stage_status']='already_connected_no_incremental_candidate'
                    out.append(inv)
                    continue
                if good:
                    inv['stage_status']='candidate_staged'
                    inv['candidate_family']='exact_unique_name_region_type_three_census_v1'
                    inv['assumption']='stable physical settlement identity where exact normalized full name, exact region and exact settlement type uniquely identify one selected source row in each census; current 2010 primary table row explicitly additive/atomic; administrative assignments can change over time; no population or boundary harmonization asserted'
                    inv['type_change_observed']=False
                    inv['administrative_context_review_needed']=bool(r.district_raw and ((o.district_raw and o.district_raw!=r.district_raw) or (m.district_raw and m.district_raw!=r.district_raw)))
                    for a,b,ya,yb in missing:
                        proposals.append({'edge_id':f'PCE-{hashlib.sha256((a+"|"+b).encode()).hexdigest()[:20]}','relation':'same_place','from_source_record_id':a,'from_year':ya,'to_source_record_id':b,'to_year':yb,
                            'candidate_status':'candidate_for_independent_review','candidate_rule':inv['candidate_family'],'candidate_basis':inv['assumption'],
                            'supporting_key':{'name_norm':r.name_norm,'region_norm':r.region_norm,'type_norm':r.type_norm,'unique_selected_endpoints_each_year':True},
                            'row_2002':{'source_record_id':o.source_record_id,'source_sha256':o.source_sha256,'source_locator':o.source_locator,'population':o.population,'name':o.settlement_name,'type':o.settlement_type,'region':o.region_raw,'district':o.district_raw},
                            'row_2010':{'source_record_id':r.source_record_id,'source_sha256':r.source_sha256,'source_locator':r.source_locator,'population':r.population,'name':r.settlement_name,'type':r.settlement_type,'region':r.region_raw,'district':r.district_raw},
                            'row_2021':{'source_record_id':m.source_record_id,'source_sha256':m.source_sha256,'source_locator':m.source_locator,'population':m.population,'name':m.settlement_name,'type':m.settlement_type,'region':m.region_raw,'district':m.district_raw},
                            'point_distance_km':None,'point_2002_origin':None,'point_2021_origin':None,
                            'legacy_flags_are_not_physical_conflicts':bool(se.get('legacy_identity_conflict',False)),'legacy_source_evidence':se,
                            'administrative_context_review_needed':inv['administrative_context_review_needed'],
                            'population_gain_candidate':r.population,'population_gain_scope':'one 2010 selected primary row, once per component; not an admission or change to population'})
                    uf.union(o.source_record_id,r.source_record_id);uf.union(r.source_record_id,m.source_record_id)
                else:
                    inv['stage_status']='hold_graph_year_collision'
                    inv['hold_reason']='adding exact-key stable-type path would create duplicate census year in component'
                    holds.append(inv)
            else:
                inv['stage_status']='hold_no_direct_point_pair_or_scope'
                inv['hold_reason']='missing accepted typed historical/physical modern point agreement <=5km, or a source row is not additive'
                holds.append(inv)
        else:
            inv['stage_status']='hold_nonunique_or_missing_exact_endpoint'
            inv['hold_reason']='exact normalized name+region does not identify one selected endpoint in each comparison year'
            holds.append(inv)
        out.append(inv)

    # Candidate family B: existing 2024 Rosstat comparative city table. This table
    # publishes the same named city row over census years; R5b links already accepted
    # are excluded. Footnote/event holds from its parser stay holds.
    t49=list(csv.DictReader(TABLE49.open(encoding='utf-8-sig')))
    accepted_pairs={(a,b) for a,b in accepted}
    table_rows=[]; t49holds=[]
    for r in t49:
        y02,y10,y21=(r[f'{y}_source_record_id'] for y in ('2002','2010','2021'))
        status=r['candidate_status_2010_2021']
        if status!='candidate_for_independent_review' or not all((y02,y10,y21)) or r['2002_match_count']!='1':
            t49holds.append({'row_id':r['row_id'],'raw_label':r['raw_russian_label'],'hold_reason':status if status!='candidate_for_independent_review' else 'missing_or_nonunique_2002_endpoint','footnote_markers':r['footnote_markers']})
            continue
        if not all(x in row_by_id for x in (y02,y10,y21)):
            t49holds.append({'row_id':r['row_id'],'raw_label':r['raw_russian_label'],'hold_reason':'source_record_id_mismatch_or_endpoint_not_current_selected','endpoint_ids':[y02,y10,y21],'footnote_markers':r['footnote_markers']})
            continue
        oldconnected=uf.connected(y02,y10) and uf.connected(y10,y21)
        if oldconnected:
            table_rows.append({'row_id':r['row_id'],'status':'already_connected_no_incremental_candidate','endpoints':[y02,y10,y21],'current_2010_population':r['2010_population'],'footnote_markers':r['footnote_markers']})
            continue
        yb_specs=[(y02,y10,2002,2010),(y10,y21,2010,2021)]
        if not path_is_safe(uf,yb_specs):
            t49holds.append({'row_id':r['row_id'],'hold_reason':'graph_duplicate_year_collision','endpoint_ids':[y02,y10,y21],'footnote_markers':r['footnote_markers']}); continue
        for a,b,ya,yb in ((y02,y10,2002,2010),(y10,y21,2010,2021)):
            if not uf.connected(a,b):
                proposals.append({'edge_id':f'PCE-YB49-{hashlib.sha256((a+"|"+b).encode()).hexdigest()[:20]}','relation':'same_place','from_source_record_id':a,'from_year':ya,'to_source_record_id':b,'to_year':yb,
                  'candidate_status':'candidate_for_independent_review','candidate_rule':'ROSSTAT2024_YB4_9_shared_city_row_identity_v1','candidate_basis':'Direct Rosstat comparative publication row carries census-year values under one exact city row; selected endpoints are exact unique publication-bound source IDs; rounded values are consistency checks only; no boundary/population harmonization asserted.',
                  'publication_row_id':r['row_id'],'publication_source_sha256':TABLE49_PDF_SHA,'raw_label':r['raw_russian_label'],'raw_table_line':r['raw_table_line'],'footnote_markers':r['footnote_markers'],
                  'from_population':row_by_id[a].population,'to_population':row_by_id[b].population,'source_hashes':[row_by_id[a].source_sha256,row_by_id[b].source_sha256],'source_locators':[row_by_id[a].source_locator,row_by_id[b].source_locator],
                  'population_gain_candidate':row_by_id[y10].population if ya==2002 else None,'population_gain_scope':'current primary 2010 endpoint counted once only if chain becomes graph-safe'})
        uf.union(y02,y10);uf.union(y10,y21)
        table_rows.append({'row_id':r['row_id'],'status':'staged_adjacent_year_edges','endpoints':[y02,y10,y21],'current_2010_population':r['2010_population'],'footnote_markers':r['footnote_markers']})

    # Write inventories and immutable candidate proposal package.
    fields_inv=sorted({k for row in out for k in row}) if out else ['source_record_id']
    write_csv(OUT/'current_primary_2010_urban_inventory.csv',out,fields_inv)
    fields_edges=sorted({k for row in proposals for k in row}) if proposals else ['edge_id','relation','from_source_record_id','from_year','to_source_record_id','to_year','candidate_status','candidate_rule']
    write_csv(OUT/'staged_identity_edges.csv',proposals,fields_edges,strict=True)
    write_csv(OUT/'disjoint_holds.csv',holds+t49holds,['source_record_id','row_id','settlement_name','raw_label','population','hold_reason','stage_status','endpoint_ids','footnote_markers','legacy_source_evidence'])
    write_csv(OUT/'table49_row_audit.csv',table_rows,['row_id','status','endpoints','current_2010_population','footnote_markers'])
    byreason=Counter(x.get('hold_reason','') for x in holds+t49holds)
    summary={
      'run_kind':'candidate staging only; no admissions or mutation to source/review/accepted ledgers',
      'input_hashes':{str(p):sha(p) for p in (SELECTED,SOURCE_EVIDENCE,POINTS,EDGES,RESIDUAL,TABLE49,CLASSIFIER,GEOKLADR)},
      'table49_pdf_sha256':TABLE49_PDF_SHA,
      'current_primary_2010_urban_residual_rows':len(out),
      'current_primary_2010_urban_residual_population':sum(float(x.get('population') or 0) for x in out),
      'staged_edge_rows':len(proposals),'staged_distinct_2010_endpoints':len({x['from_source_record_id'] for x in proposals if x['from_year']==2010}|{x['to_source_record_id'] for x in proposals if x['to_year']==2010}),
      'staged_2010_population_once':sum(float(v) for v in {x['from_source_record_id'] if x['from_year']==2010 else x['to_source_record_id']:x.get('population_gain_candidate') for x in proposals if x.get('population_gain_candidate') is not None}.values()),
      'staged_rule_counts':dict(Counter(x['candidate_rule'] for x in proposals)),
      'hold_count':len(holds)+len(t49holds),'hold_reason_counts':dict(byreason),
      'table49_row_audit_counts':dict(Counter(x['status'] for x in table_rows)),
      'limits':['Candidate population sums are conditional source-value mass only, not admissions, projections, comparable-population estimates or national coverage claims.','The accepted graph was respected for duplicate-year safety.','No fuzzy names, proximity-only, equal-population, or old legacy pointer was used as identity evidence.','No raw source downloads were performed.'],
    }
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True))

if __name__=='__main__': main()
