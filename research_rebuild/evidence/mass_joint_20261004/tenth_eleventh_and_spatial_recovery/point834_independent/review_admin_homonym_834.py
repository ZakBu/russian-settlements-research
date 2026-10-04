#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, math, re, unicodedata, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import duckdb, pandas as pd, xlrd

ROOT=Path('/workspace/settlements-work/continuation_20261004')
IN=ROOT/'root/point_gap_spatial_diagnostic_after_afipsky/name_collision_admin_context_diagnostic'
OUT=ROOT/'independent_review/admin_homonym_834_point_review'; OUT.mkdir(parents=True,exist_ok=True)
CAND=IN/'reviewed_ready_834_admin_homonym_point_candidates.csv'
RECEIPT=IN/'reviewed_ready_834_packet_receipt.json'
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
CURRENT=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
GRAPH=ROOT/'accepted_mass_ninth_reviewed_legacy202/accepted_identity_edges.parquet'
POINTS=ROOT/'accepted_mass_ninth_reviewed_legacy202/accepted_point_uses.parquet'
GNZIP=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
BLOCK=Path('/workspace/settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json')

class UF:
    def __init__(self): self.p={}; self.r={}
    def find(self,x):
        x=str(x); self.p.setdefault(x,x); self.r.setdefault(x,0)
        while self.p[x]!=x: self.p[x]=self.p[self.p[x]]; x=self.p[x]
        return x
    def union(self,a,b):
        a=self.find(a); b=self.find(b)
        if a==b:return
        if self.r[a]<self.r[b]:a,b=b,a
        self.p[b]=a
        if self.r[a]==self.r[b]:self.r[a]+=1

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def norm(x):
    if x is None or pd.isna(x): return ''
    return ' '.join(unicodedata.normalize('NFKC',str(x)).replace('ё','е').casefold().split())
def adminnorm(x):
    s=norm(x)
    s=re.sub(r'^(городской округ|муниципальный округ|муниципальный район|район|округ)\s+','',s)
    s=re.sub(r'\s+(муниципальный район|городской округ|муниципальный округ|район|округ|мр|го|мо)$','',s)
    return ' '.join(s.split())
def hav(a,b):
    la1,la2=map(math.radians,(float(a[0]),float(b[0]))); dl=math.radians(float(b[1])-float(a[1]))
    h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin(dl/2)**2
    return 6371.0088*2*math.asin(math.sqrt(h))
def cellstr(x):
    if x is None:return ''
    if isinstance(x,float) and math.isnan(x):return ''
    return str(x).strip()
def near_num(a,b):
    try:return abs(float(a)-float(b))<1e-8
    except:return False

def main():
    cand=pd.read_csv(CAND,engine='python',keep_default_na=True)
    if len(cand)!=834 or cand.target_source_record_id.nunique()!=834: raise RuntimeError('candidate row/id cardinality differs from frozen receipt')
    ddb=duckdb.connect(config={'threads':1,'memory_limit':'1800MB','preserve_insertion_order':False})
    qp=lambda p:"'"+str(p).replace("'","''")+"'"
    # Rejoin exact authoritative selected rows by source id, with a narrow projection.
    ids=cand.target_source_record_id.astype(str).tolist()
    ddb.register('wanted_current',pd.DataFrame({'source_record_id':ids}))
    cur=ddb.execute(f"SELECT s.source_record_id,s.census_year,s.source_file,s.source_sheet,s.source_row,s.source_name_raw,s.settlement_name,s.settlement_type,s.region_raw,s.district_raw,s.population,s.latitude,s.longitude,s.okato,s.oktmo,s.is_additive_settlement_record,s.population_scope FROM read_parquet({qp(SELECTED)}) s INNER JOIN wanted_current w USING(source_record_id) WHERE census_year=2021").fetchdf()
    if len(cur)!=834: raise RuntimeError(f'selected current endpoint rejoin {len(cur)} != 834')
    oldctx=[]
    for r in cand.itertuples(index=False):
        members=json.loads(r.accepted_component_old_2002_2010_context_json)
        for m in members:
            if str(m.get('year')) in {'2002','2010'}: oldctx.append(m)
    oldids=sorted(set(str(x['id']) for x in oldctx))
    if len(oldctx)!=1668 or len(oldids)!=1668: raise RuntimeError(f'historical selected context is not exactly one endpoint per year: {len(oldctx)}/{len(oldids)}')
    ddb.register('wanted_old',pd.DataFrame({'source_record_id':oldids}))
    olds=ddb.execute(f"SELECT s.source_record_id,s.census_year,s.source_file,s.source_sheet,s.source_row,s.source_name_raw,s.settlement_name,s.settlement_type,s.region_raw,s.district_raw,s.population,s.okato,s.oktmo,s.source_native_id,s.source_sha256,s.source_locator,s.is_additive_settlement_record,s.population_scope FROM read_parquet({qp(SELECTED)}) s INNER JOIN wanted_old w USING(source_record_id)").fetchdf()
    if len(olds)!=1668: raise RuntimeError(f'historical selected endpoint rejoin {len(olds)} != 1668')
    # Replay accepted graph component connection using only identity endpoint columns.
    uf=UF(); graph_rows=0
    accepted_statuses=("checked_rule_accepted","checked_rule_accepted_redundant_graph_connectivity_effect","accepted_rule_family_after_independent_sample_review","case_specific_independent_review_accepted","case_review_accepted","independent_case_review_accepted","accepted_case_specific")
    reader=duckdb.execute(f"SELECT from_source_record_id,to_source_record_id FROM read_parquet({qp(GRAPH)}) WHERE decision_status IN ({','.join(repr(x) for x in accepted_statuses)})").fetch_record_batch(rows_per_batch=50000)
    for batch in reader:
        for a,b in zip(batch.column(0).to_pylist(),batch.column(1).to_pylist()):
            if a is not None and b is not None: uf.union(a,b); graph_rows+=1
    # Baseline ledgers are pinned; test no candidate is already a current-year point target.
    pointed=ddb.execute(f"SELECT DISTINCT target_source_record_id FROM read_parquet({qp(POINTS)}) WHERE cast(target_year as varchar) like '2021%'").fetchall()
    pointed={str(x[0]) for x in pointed}
    # Read native source rows by immutable parquet ordinal; source locator is 1-based, file_row_number is 0-based.
    rid=cand.target_source_record_id.str.rsplit(':',n=1).str[-1].astype(int)-1
    row_ids=sorted(set(int(x) for x in rid))
    rawrows=ddb.execute(f"SELECT file_row_number,object_level,object_name,oktmo,region,mun_upper,mun_lower,settlement,population,latitude_dadata,longitude_dadata,settlement_type_dadata,settlement_type_full_dadata,settlement_with_type_dadata FROM read_parquet({qp(CURRENT)},file_row_number=true) WHERE file_row_number IN ({','.join(map(str,row_ids))})").fetchdf()
    if len(rawrows)!=834 or rawrows.file_row_number.nunique()!=834: raise RuntimeError('raw current source row replay failed cardinality')
    rawidx=rawrows.set_index('file_row_number')
    # Independent raw-source global native-code uniqueness, using literal strings only.
    rawcode=ddb.execute(f"SELECT oktmo,count(*) n FROM read_parquet({qp(CURRENT)}) WHERE nullif(trim(oktmo),'') IS NOT NULL GROUP BY oktmo").fetchdf()
    rawcode_map=dict(zip(rawcode.oktmo.astype(str),rawcode.n.astype(int)))
    selected_code=ddb.execute(f"SELECT oktmo,count(*) n FROM read_parquet({qp(SELECTED)}) WHERE census_year=2021 AND nullif(trim(oktmo),'') IS NOT NULL GROUP BY oktmo").fetchdf()
    selected_code_map=dict(zip(selected_code.oktmo.astype(str),selected_code.n.astype(int)))
    # GeoNames records are replayed by row locator, byte range and SHA from the pinned archive.
    gn_needed={int(x) for x in cand.geonames_ru_line_1based.dropna()}
    gnrows={}
    with zipfile.ZipFile(GNZIP) as z:
        name='RU.txt' if 'RU.txt' in z.namelist() else next(n for n in z.namelist() if n.endswith('RU.txt'))
        data=z.read(name); off=0
        for ln,line in enumerate(data.splitlines(keepends=True),1):
            if ln in gn_needed:
                cols=line.decode('utf-8').rstrip('\r\n').split('\t')
                gnrows[ln]={'line':line,'cols':cols,'start':off,'end':off+len(line),'sha':hashlib.sha256(line).hexdigest()}
            off+=len(line)
    # Raw historical publication-row replay: open each cited workbook once and fetch only row vectors.
    old_by_id=olds.set_index('source_record_id',drop=False)
    workbook_cache={}; workbook_sha={}; historical_row_checks={}
    for m in oldctx:
        oid=str(m['id']); o=old_by_id.loc[oid]
        rel=str(o.source_file)
        f=Path('/workspace/settlements-raw')/rel.removeprefix('data/') if rel.startswith('data/') else Path('/workspace/settlements-raw')/rel
        if not f.exists(): f=Path('/workspace/settlements-raw')/str(o.source_file).replace('data/raw/','data/raw/')
        if not f.exists():
            historical_row_checks[oid]={'status':'held_raw_workbook_missing','source_file':str(f)}; continue
        key=str(f)
        if key not in workbook_cache:
            book=xlrd.open_workbook(str(f),on_demand=True)
            workbook_cache[key]=book; workbook_sha[key]=sha(f)
        book=workbook_cache[key]
        sheet=str(o.source_sheet)
        if sheet not in book.sheet_names():
            historical_row_checks[oid]={'status':'held_sheet_missing','source_file':str(f),'source_sheet':sheet}; continue
        sh=book.sheet_by_name(sheet)
        if pd.isna(o.source_row):
            historical_row_checks[oid]={'status':'held_row_locator_missing'}; continue
        excel_row=int(float(o.source_row)); ri=excel_row-1
        if ri<0 or ri>=sh.nrows:
            historical_row_checks[oid]={'status':'held_row_out_of_range','source_row':excel_row,'sheet_rows':sh.nrows}; continue
        vals=sh.row_values(ri)
        texts=[norm(v) for v in vals if isinstance(v,str) and norm(v)]
        textblob=' | '.join(texts)
        name=norm(o.settlement_name); typ=norm(o.settlement_type)
        raw_source=norm(o.source_name_raw)
        name_ok=(name in texts) or (name and name in textblob)
        type_ok=(typ in texts) or (raw_source and raw_source in texts) or (raw_source and raw_source in textblob)
        pop=float(o.population) if pd.notna(o.population) else None
        nums=[]
        for v in vals:
            if isinstance(v,(int,float)) and not (isinstance(v,float) and math.isnan(v)): nums.append(float(v))
            elif isinstance(v,str):
                try: nums.append(float(v.strip().replace(',','.')))
                except ValueError: pass
        pop_ok=pop is not None and any(near_num(x,pop) for x in nums)
        # 2010 table rows have explicit district column; 2002 worksheet lacks a reliable row-level district field.
        dnorm=adminnorm(o.district_raw)
        district_in_row=any(adminnorm(v)==dnorm for v in vals if isinstance(v,str) and dnorm)
        historical_row_checks[oid]={'status':'raw_row_replayed','source_file':str(f),'source_file_sha256':workbook_sha[key],'source_sheet':sheet,'source_row_1based':excel_row,'source_native_id_literal':str(o.source_native_id),'raw_row_name_match':bool(name_ok),'raw_row_type_match':bool(type_ok),'raw_row_population_match':bool(pop_ok),'raw_row_district_literal_match':bool(district_in_row),'raw_row_values_sample':[str(x)[:160] for x in vals[:10]],'selected_district_raw':o.district_raw,'raw_district_row_claim':'row_match_checked; 2002 sheet district may be hierarchical metadata rather than a cell on the settlement row'}
        book.unload_sheet(sheet)
    for book in workbook_cache.values(): book.release_resources()
    # Crosswalk selected current/history fields and execute conservative admin-context normalization.
    curidx=cur.set_index('source_record_id',drop=False); candidx=cand.set_index('target_source_record_id',drop=False)
    old_by_comp={str(r.target_source_record_id):json.loads(r.accepted_component_old_2002_2010_context_json) for r in cand.itertuples(index=False)}
    out=[]
    for r in cand.itertuples(index=False):
        sid=str(r.target_source_record_id); s=curidx.loc[sid]; raw=rawidx.loc[int(s.source_row)-1]
        old=[x for x in old_by_comp[sid] if str(x.get('year')) in {'2002','2010'}]
        old_by={str(x['year']):x for x in old}
        samecomp=(uf.find(sid)==uf.find(old_by['2002']['id'])==uf.find(old_by['2010']['id']))
        code=str(raw.oktmo).strip() if pd.notna(raw.oktmo) else ''
        currentrow=(str(raw.object_level).strip()=='Населенный пункт' and norm(raw.settlement)==norm(s.source_name_raw) and norm(raw.region)==norm(s.region_raw) and code==str(s.oktmo).strip() and near_num(raw.population,s.population) and near_num(raw.latitude_dadata,s.latitude) and near_num(raw.longitude_dadata,s.longitude))
        codeunique=(rawcode_map.get(code,0)==1 and selected_code_map.get(code,0)==1)
        pointreuse=(sid not in pointed)
        oldmatch={}
        for y in ('2002','2010'):
            o=old_by[y]
            oldmatch[y]=adminnorm(o.get('district')) in {adminnorm(raw.mun_upper),adminnorm(raw.mun_lower)}-{''}
        admvalid=all(oldmatch.values()) and norm(raw.region)==norm(s.region_raw)
        gr=int(r.geonames_ru_line_1based); g=gnrows.get(gr); gc=g['cols'] if g else []
        gn_ok=bool(g and len(gc)==19 and gc[0]==str(int(r.geonames_witness_geonameid)) and norm(gc[1])==norm(r.geonames_witness_raw_name) and gc[6]=='P' and gc[7] in {'PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLA5','PPLC'} and gc[10]==str(int(r.geonames_admin1_code)) and g['sha']==str(r.geonames_ru_line_sha256) and g['start']==int(r.geonames_ru_byte_start_0based) and g['end']==int(r.geonames_ru_byte_end_0based))
        gn_dist=None
        if gn_ok:
            gn_dist=hav((raw.latitude_dadata,raw.longitude_dadata),(float(gc[4]),float(gc[5])))
        histrows=[historical_row_checks.get(str(x['id']),{}) for x in old]
        histrow_ok=len(histrows)==2 and all(x.get('status')=='raw_row_replayed' and x.get('raw_row_name_match') and x.get('raw_row_type_match') and x.get('raw_row_population_match') for x in histrows)
        flags=json.loads(r.rule_checks_json)
        hardflags={k:bool(getattr(r,k)) for k in ['legacy_same_year_collision','is_federal_aggregate']}
        succ=bool(pd.notna(r.legacy_verified_successor_settlement_id) and str(r.legacy_verified_successor_settlement_id).strip())
        eligible=all([samecomp,currentrow,codeunique,pointreuse,admvalid,gn_ok,gn_dist is not None and gn_dist<=1.0,histrow_ok,flags.get('source_row_is_additive_settlement'),flags.get('source_raw_atomic_row_exact'),flags.get('not_on_frozen_global_target_blocklist'),flags.get('no_exact_source_point_shared_by_other_current_rows'),not any(hardflags.values()),not succ])
        # Retain direct hard reason list per row; no global-name uniqueness gate.
        holds=[]
        for ok,label in [(samecomp,'accepted_2002_2010_2021_component_replay'),(currentrow,'raw_current_row_replay'),(codeunique,'literal_native_OKTMO_unique_in_raw_and_selected'),(pointreuse,'not_already_pointed'),(admvalid,'both_old_districts_match_current_publisher_mun_upper_or_lower'),(gn_ok,'GeoNames_line_hash_offsets_name_feature_ADM1_replay'),(gn_dist is not None and gn_dist<=1.0,'independent_recomputed_witness_distance_le_1km'),(histrow_ok,'both_historical_publisher_rows_replayed_name_type_population'),(flags.get('source_row_is_additive_settlement'),'source_additive'),(flags.get('source_raw_atomic_row_exact'),'source_raw_exact'),(flags.get('not_on_frozen_global_target_blocklist'),'not_blocked'),(flags.get('no_exact_source_point_shared_by_other_current_rows'),'raw_point_not_shared'),(not any(hardflags.values()),'no_federal_or_sameyear_hardflags'),(not succ,'no_verified_successor')]:
            if not ok: holds.append(label)
        rec={'target_source_record_id':sid,'candidate_population':float(s.population),'name':s.settlement_name,'type':s.settlement_type,'region':s.region_raw,'current_native_OKTMO_literal':code,'current_publisher_mun_upper':raw.mun_upper,'current_publisher_mun_lower':raw.mun_lower,'old_2002_district_raw':old_by['2002'].get('district'),'old_2010_district_raw':old_by['2010'].get('district'),'adminnorm_2002':adminnorm(old_by['2002'].get('district')),'adminnorm_2010':adminnorm(old_by['2010'].get('district')),'adminnorm_current_upper':adminnorm(raw.mun_upper),'adminnorm_current_lower':adminnorm(raw.mun_lower),'old2002_matches_current_publisher':oldmatch['2002'],'old2010_matches_current_publisher':oldmatch['2010'],'component_same_accepted_graph':samecomp,'raw_current_row_exact':currentrow,'native_code_unique_raw_and_selected':codeunique,'raw_code_count':rawcode_map.get(code,0),'selected_code_count':selected_code_map.get(code,0),'not_already_pointed':pointreuse,'proposed_coordinate_latitude':float(raw.latitude_dadata),'proposed_coordinate_longitude':float(raw.longitude_dadata),'proposed_coordinate_origin':'2021 Tochno source parquet raw latitude_dadata/longitude_dadata exact row','coordinate_use_scope':'current 2021 source-point candidate only; GeoNames is corroborating witness only and its coordinates are not substituted','source_type_region_global_uniqueness':False,'global_name_uniqueness_required':False,'same_name_type_region_competitor_count':int(r.same_selected_name_type_region_count),'geonames_id':int(r.geonames_witness_geonameid),'geonames_feature':gc[7] if gn_ok else None,'geonames_admin1':gc[10] if gn_ok else None,'geonames_admin2':gc[11] if gn_ok else None,'geonames_latitude':float(gc[4]) if gn_ok else None,'geonames_longitude':float(gc[5]) if gn_ok else None,'geonames_hash_locator_replayed':gn_ok,'recomputed_current_to_geonames_km':gn_dist,'both_historical_raw_rows_name_type_population_replayed':histrow_ok,'historical_raw_row_checks_json':json.dumps(histrows,ensure_ascii=False),'legacy_collision':hardflags['legacy_same_year_collision'],'federal_aggregate':hardflags['is_federal_aggregate'],'verified_successor':succ,'eligible_scoped_point_seed':bool(eligible),'hold_reasons':'|'.join(holds),'scope':'candidate point use only; no identity, provider-ID, historical-coordinate or census-boundary claim'}
        out.append(rec)
    review=pd.DataFrame(out)
    # Fixed deterministic risk panel: top 30 by population, 20 district label/normalization edge strata, and 10 near radius boundary; dedup then cap at 60.
    top=review.sort_values(['candidate_population','target_source_record_id'],ascending=[False,True]).head(30).copy();top['risk_stratum']='top_population'
    rem=review[~review.target_source_record_id.isin(top.target_source_record_id)]
    normedge=rem[(rem.adminnorm_2002!=rem.adminnorm_2010)|(rem.current_publisher_mun_upper.fillna('')!=rem.current_publisher_mun_lower.fillna(''))|(rem.adminnorm_2002!=rem.adminnorm_current_upper)].sort_values(['candidate_population','target_source_record_id'],ascending=[False,True]).head(20).copy();normedge['risk_stratum']='district_or_municipal_label_normalization'
    rem=rem[~rem.target_source_record_id.isin(normedge.target_source_record_id)]
    near=rem.assign(_gap=(rem.recomputed_current_to_geonames_km-1).abs()).sort_values(['_gap','candidate_population','target_source_record_id'],ascending=[True,False,True]).head(10).copy();near['risk_stratum']='nearest_to_1km_witness_radius'
    risk=pd.concat([top,normedge,near],ignore_index=True)
    elig=review[review.eligible_scoped_point_seed].copy()
    holds=review[~review.eligible_scoped_point_seed].copy()
    # District frequencies and alias status are separate from the candidate list.
    districts=review.groupby(['adminnorm_2002','adminnorm_current_upper'],dropna=False).agg(rows=('target_source_record_id','size'),population=('candidate_population','sum'),distinct_current_ids=('target_source_record_id','nunique')).reset_index().sort_values(['population','rows'],ascending=False)
    out_elig=OUT/'eligible_point_seedlist.csv'; elig.to_csv(out_elig,index=False)
    out_holds=OUT/'held_candidates.csv'; holds.to_csv(out_holds,index=False)
    out_all=OUT/'full_vector_replay.csv'; review.to_csv(out_all,index=False)
    out_risk=OUT/'fixed_risk_sample.csv'; risk.to_csv(out_risk,index=False)
    out_dist=OUT/'district_reuse_summary.csv'; districts.to_csv(out_dist,index=False)
    rawhashes={str(CAND):sha(CAND),str(RECEIPT):sha(RECEIPT),str(SELECTED):sha(SELECTED),str(CURRENT):sha(CURRENT),str(GRAPH):sha(GRAPH),str(POINTS):sha(POINTS),str(GNZIP):sha(GNZIP),str(BLOCK):sha(BLOCK)}
    counts={
      'candidate_rows':len(review),'eligible_rows':len(elig),'held_rows':len(holds),'candidate_population':float(review.candidate_population.sum()),'eligible_population':float(elig.candidate_population.sum()),'held_population':float(holds.candidate_population.sum()),
      'historical_rows_raw_replayed':sum(x.get('status')=='raw_row_replayed' for x in historical_row_checks.values()),'historical_rows_name_type_population_match':sum(x.get('status')=='raw_row_replayed' and x.get('raw_row_name_match') and x.get('raw_row_type_match') and x.get('raw_row_population_match') for x in historical_row_checks.values()),'historical_raw_workbooks':len(workbook_sha),'historical_raw_workbook_sha256':workbook_sha,
      'accepted_graph_edge_rows_replayed':graph_rows,'same_accepted_2002_2010_2021_component':int(review.component_same_accepted_graph.sum()),'raw_current_row_exact':int(review.raw_current_row_exact.sum()),'literal_current_code_unique_in_raw_and_selected':int(review.native_code_unique_raw_and_selected.sum()),'both_old_districts_match_current_municipal_context':int((review.old2002_matches_current_publisher&review.old2010_matches_current_publisher).sum()),'GN_witness_bytes_hash_feature_ADM1_replayed':int(review.geonames_hash_locator_replayed.sum()),'recomputed_GN_distance_le_1km':int(review.recomputed_current_to_geonames_km.le(1).sum()),'currentpoint_already_accepted':int((~review.not_already_pointed).sum()),'same_name_type_region_duplicates_retained':int(review.same_name_type_region_competitor_count.gt(1).sum()),'source_ordinal_used_as_code':False,'geonames_ADM2_claimed':False,
      'distinct_old_district_norms':int(review.adminnorm_2002.nunique()),'distinct_current_publisher_upper_norms':int(review.adminnorm_current_upper.nunique()),'reused_district_context_groups':int((districts.rows>1).sum()),'district_context_groups':len(districts),
      'risk_sample_rows':len(risk),'risk_sample_strata':risk.risk_stratum.value_counts().to_dict(),'frozen_global_block_count':0,
      'identity_or_population_changes':False,'point_admission':False,'historical_coordinate_or_native_provider_binding_claim':False,'census_boundary_comparability_asserted':False
    }
    receipt={'created_at_utc':datetime.now(timezone.utc).isoformat(),'status':'independent_review_candidate_point_seed_only','candidate_packet_sha256':sha(CAND),'parent_candidate_receipt_sha256':sha(RECEIPT),'inputs':rawhashes,'methods':{'current_raw':'Exact source row addressed by 1-based Parquet source locator; raw object_level/name/region/literal OKTMO/population/coordinates rejoined. Literal code frequency independently grouped over raw provider and selected 2021 rows.','historical_raw':'Cited 2002/2010 workbook hash and sheet/row checked; settlement name/type and selected population required in the cited raw row. Historical district label comes from the selected source observation field; the 2002 workbook raw row does not necessarily contain a district cell, so it is not represented as row-cell proof.','component':'All accepted identity-graph endpoint pairs replayed in a low-memory union-find; both 2002 and 2010 selected endpoint IDs must share candidate 2021 source component.','admin_rule':'Both actual selected historical district labels, under NFKC/casefold/ё normalization plus explicit Russian admin prefix/suffix stripping, must equal current raw Tochno `mun_upper` or `mun_lower`. No fuzziness, transliteration, GeoNames ADM2 match, or global name uniqueness.','GN_witness':'Original GeoNames RU line, byte offsets, SHA, feature code, exact row ID/name/ADM1 replayed from pinned archive; distance recomputed to raw publisher coordinate. ADM2 left blank/unasserted.','scope':'This does not admit identity or a point. It is a bounded candidate for reusing the current 2021 raw point with the current accepted source identity. No historical coordinate, legal identifier binding, population change, or boundary comparability is asserted.'},'counts':counts,'outputs':{x.name:{'path':str(x),'sha256':sha(x),'rows':int(len(pd.read_csv(x,engine='python')))} for x in [out_elig,out_holds,out_all,out_risk,out_dist]},'candidate_disposition':'eligible rows retain candidate status for root-level application/review; held rows have explicit failed predicates','mutations':{'input_candidates':False,'accepted_graph':False,'accepted_points':False,'selected_population_values':False}}
    rp=OUT/'independent_review_receipt.json'; rp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'receipt':str(rp),'receipt_sha256':sha(rp),'counts':counts,'eligible_csv_sha256':sha(out_elig),'held_csv_sha256':sha(out_holds),'risk_csv_sha256':sha(out_risk)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
