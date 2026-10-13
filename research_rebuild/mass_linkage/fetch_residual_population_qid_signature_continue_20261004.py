#!/usr/bin/env python3
"""Continue broad fetch-only residual QID population-signature candidates.

The source pair ledger is frozen. This continuation widens only the fetch gate:
current source/QID/native point proof plus any typed old pair alternative. Unique
signature and population quality requirements remain review/admission gates.
"""
from pathlib import Path
import hashlib, json, time, urllib.request, urllib.parse, urllib.error, argparse
import pandas as pd
from research_rebuild.mass_linkage.stage_residual_population_qid_signature_mass_20261004 import (
    R4, OUT, PAIR_CHECKPOINT, ENT, entities_for, evaluate_signatures,
    sha, sha_bytes, utc, p31_qids, physical_lineage, norm, digits
)
from research_rebuild.mass_linkage.coordinate_validation_packet import wikidata_type_lineage

EXP=OUT/'expanded_fetch'
RAWDIR=OUT/'raw_entity_batches'
ROOTS=[R4/'wide_qid_homonym_full_entity_retrieval_20261004/entity_fetch_and_replay',R4/'wide_qid_homonym_full_entity_retrieval_20261004_v2/entity_fetch_and_replay',R4/'ten_digit_oktmo_temporal_recovery_20261004']
P31_META=Path('/workspace/settlements-work/coordinates/validation_packet/wikidata_type_hierarchy_v1/ancestry_metadata.json')
SEED=20261004
COLS=['wikidata_qid','current_source_record_id','current_population','current_region_raw','current_district_raw','current_name_raw','current_type_raw','current_native_oktmo_digits','old_2002_source_record_id','old_2002_population','old_2010_source_record_id','old_2010_population','current_to_2002_uf_outcome','current_to_2010_uf_outcome','any_event_exact_native_code_guard','old_2002_population_quality','old_2010_population_quality','old_2010_confidentiality_perturbed']

def raw_cached():
    found=set()
    for root in ROOTS:
        for path in root.glob('raw_entity_batch_*.json'):
            try: found.update(json.loads(path.read_text()).get('entities',{}))
            except Exception: pass
    return {str(q) for q in found}
def current_raw_qids():
    found=set()
    for path in RAWDIR.glob('raw_entity_batch_*.json'):
        found.update(json.loads(path.read_text()).get('entities',{}))
    return {str(q) for q in found}
def rank_broad_candidates():
    cache=EXP/'broad_qid_ranked_pool.csv'
    if cache.exists():
        return pd.read_csv(cache,dtype={'wikidata_qid':str},low_memory=False)
    # Do not gate fetching on signature uniqueness or direct/official population
    # quality. Retain only edges that are not already structurally impossible.
    pieces=[]
    for x in pd.read_csv(PAIR_CHECKPOINT,usecols=COLS,dtype={'wikidata_qid':str},chunksize=100000,low_memory=False):
        x=x[~x.any_event_exact_native_code_guard.fillna(True)]
        x=x[~x.current_to_2002_uf_outcome.eq('year_constrained_collision')&~x.current_to_2010_uf_outcome.eq('year_constrained_collision')]
        if not len(x): continue
        x['fetch_priority_mass']=pd.to_numeric(x.current_population,errors='coerce').fillna(0)+pd.to_numeric(x.old_2002_population,errors='coerce').fillna(0)+pd.to_numeric(x.old_2010_population,errors='coerce').fillna(0)
        g=x.groupby('wikidata_qid',as_index=False).agg(current_source_record_id=('current_source_record_id','first'),current_population=('current_population','first'),current_region_raw=('current_region_raw','first'),current_district_raw=('current_district_raw','first'),current_name_raw=('current_name_raw','first'),current_type_raw=('current_type_raw','first'),current_native_oktmo_digits=('current_native_oktmo_digits','first'),source_pair_alternatives=('old_2002_source_record_id','size'),priority_mass=('fetch_priority_mass','max'))
        pieces.append(g)
    if not pieces: return pd.DataFrame()
    agg=pd.concat(pieces,ignore_index=True).groupby('wikidata_qid',as_index=False).agg(current_source_record_id=('current_source_record_id','first'),current_population=('current_population','first'),current_region_raw=('current_region_raw','first'),current_district_raw=('current_district_raw','first'),current_name_raw=('current_name_raw','first'),current_type_raw=('current_type_raw','first'),current_native_oktmo_digits=('current_native_oktmo_digits','first'),source_pair_alternatives=('source_pair_alternatives','sum'),priority_mass=('priority_mass','max'))
    agg['region_stratum']=agg.current_region_raw.fillna('').astype(str)
    agg=agg.sort_values(['priority_mass','current_population','wikidata_qid'],ascending=[False,False,True],kind='mergesort').reset_index(drop=True)
    agg.insert(0,'fetch_rank',range(1,len(agg)+1))
    agg.to_csv(cache,index=False)
    return agg

def retry_fetch(qids):
    # Respect API load; bounded retries only for transport/transient failures.
    params={'action':'wbgetentities','ids':'|'.join(qids),'props':'claims|labels|descriptions','languages':'ru|en','format':'json','formatversion':'2'}
    url='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'User-Agent':'RussianSettlementsResearch/1.0 (open research data reconciliation)'})
    for attempt,delay in enumerate((0.5,2,5)):
        try:
            with urllib.request.urlopen(req,timeout=45) as response:
                body=response.read(); status=response.status; final=response.geturl()
            if status!=200 or not final.startswith('https://www.wikidata.org/'):
                raise RuntimeError(f'unexpected Wikidata response {status}: {final}')
            return url,final,status,body
        except urllib.error.HTTPError as e:
            if attempt==2 or e.code not in (429,500,502,503,504): raise
            time.sleep(delay)
        except Exception:
            if attempt==2: raise
            time.sleep(delay)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=1500,help='new QIDs to fetch in this round')
    parser.add_argument('--checkpoint-every-batches',type=int,default=10)
    parser.add_argument('--request-name',default='expanded_fetch_request_next.csv')
    args=parser.parse_args()
    EXP.mkdir(parents=True,exist_ok=True); RAWDIR.mkdir(parents=True,exist_ok=True)
    pre_raw=raw_cached(); full_cache=set(pd.read_parquet(ENT,columns=['wikidata_qid']).wikidata_qid.astype(str))
    already=current_raw_qids()
    ranked=rank_broad_candidates()
    ranked=ranked[~ranked.wikidata_qid.astype(str).isin(pre_raw|full_cache)].copy()
    # Current 500-QID strict pilot/run are valid broad fetches and count toward
    # the bounded 2,000-entity read; never request them again.
    selected=[]; union=set(already)
    for r in ranked.to_dict('records'):
        q=str(r['wikidata_qid'])
        if q in union: continue
        selected.append(r); union.add(q)
        if len(selected)>=args.limit: break
    request=pd.DataFrame(selected)
    request.insert(0,'fetch_order',range(len(already)+1,len(already)+len(request)+1))
    request['candidate_only']=True; request['population_admitted']=False; request['identity_admitted']=False
    request['fetch_rule']='accepted_current_point_plus_exact_current_P764_physical_P31_and_any_typed_2002_2010_source_pair_alternative; no_unique_signature_or_source_quality_fetch_gate'
    request_path=EXP/args.request_name
    request.to_csv(request_path,index=False)
    (EXP/(request_path.stem+'_plan.json')).write_text(json.dumps({'status':'fetch_plan_candidate_only_no_admission','created_utc':utc(),'seed':SEED,'already_fetched_qids':len(already),'prior_raw_cache_qids':len(pre_raw),'structured_entity_cache_qids':len(full_cache),'ranked_broad_qids':len(ranked),'new_qids_requested':len(request),'source_pair_checkpoint_sha256':sha(PAIR_CHECKPOINT),'baseline_graph_sha256':'cc62fc8d3184c43f6ce09cea0ce71618077347ea4dee0f53ad9709f5c20a8241','baseline_points_sha256':'a67529375e63391e7d05e3ab902ff20884ec3fd4483c7b0bbc988ca056b3c994','fetch_only_rule':'current accepted point and exact current native P764/physical P31/WIDE name-type-region plus any actual typed old source-pair alternative; event/collision guards retained; source quality and unique exact P1082 pair are downstream candidate review gates, not fetch gates','request_sha256':sha(request_path)},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'already_fetched':len(already),'prior_raw_cache':len(pre_raw),'full_entity_cache':len(full_cache),'broad_qids':len(ranked),'new_requested':len(request),'request_file':str(request_path),'first50_gross_priority_mass':int(request.head(50).priority_mass.sum()) if len(request) else 0},ensure_ascii=False),flush=True)
    if not len(request): return
    # Cache the projected source-pair signature index after the first read so
    # network resumes never reparse the large frozen CSV.
    pair_index=EXP/'source_pair_signature_eval_index.parquet'
    pair_cols=['wikidata_qid','current_source_record_id','current_population','current_name_raw','current_type_raw','current_native_oktmo_digits','old_2002_source_record_id','old_2002_population','old_2002_confidentiality_perturbed','old_2010_source_record_id','old_2010_population','old_2010_confidentiality_perturbed','current_to_2002_uf_outcome','current_to_2010_uf_outcome','any_event_exact_native_code_guard']
    if pair_index.exists(): pairs=pd.read_parquet(pair_index)
    else:
        pairs=pd.read_csv(PAIR_CHECKPOINT,usecols=pair_cols,dtype={'wikidata_qid':str,'current_native_oktmo_digits':str},low_memory=False)
        pairs.to_parquet(pair_index,index=False,compression='zstd')
        (EXP/'source_pair_signature_eval_index_manifest.json').write_text(json.dumps({'status':'projected_review_index_read_only','source_pair_checkpoint_sha256':sha(PAIR_CHECKPOINT),'rows':len(pairs),'columns':pair_cols,'output_sha256':sha(pair_index),'output_bytes':pair_index.stat().st_size},ensure_ascii=False,indent=2)+'\n')
    qids=request.wikidata_qid.astype(str).tolist()
    batch_meta=[]
    existing=sorted(RAWDIR.glob('raw_entity_batch_*.json'))
    next_num=max([int(p.stem.split('_')[-1]) for p in existing]+[0])+1
    profiles=wikidata_type_lineage(json.loads(P31_META.read_text(encoding='utf-8')))
    round_dir=EXP/'round2_progress'; round_dir.mkdir(exist_ok=True)
    base_ledger=pd.read_csv(EXP/'final_candidate_packet/all_2000_qid_signature_screen.csv',low_memory=False)
    # Reconstruct two earlier 500-QID signature increments from preserved raw
    # entities/checkpoints once; this avoids rereading any completed QID again.
    previous_request_path=EXP/'expanded_fetch_request_next5000.csv'
    if previous_request_path.exists():
        previous_request=pd.read_csv(previous_request_path,dtype={'wikidata_qid':str})
        completed=set(current_raw_qids())
        previous_qids=previous_request.wikidata_qid.astype(str).tolist()
        first500=set(previous_qids[:500]); middle500=set(previous_qids[500:1000])
        old_checkpoint=EXP/'progress_2500/signature_review_candidates.csv'
        inc_first=round_dir/'signature_increment_002500.csv'
        if old_checkpoint.exists() and not inc_first.exists() and first500.issubset(completed):
            old=pd.read_csv(old_checkpoint,low_memory=False)
            first=old[old.wikidata_qid.astype(str).isin(first500)].copy()
            first['candidate_only']=True;first['identity_admitted']=False;first['population_admitted']=False
            first.to_csv(inc_first,index=False)
        inc_middle=round_dir/'signature_increment_003000.csv'
        if not inc_middle.exists() and middle500.issubset(completed):
            p_mid=pairs[pairs.wikidata_qid.astype(str).isin(middle500)].copy()
            mid=pd.DataFrame(evaluate_signatures(sorted(middle500),RAWDIR,p_mid,profiles))
            if len(mid):mid['candidate_only']=True;mid['identity_admitted']=False;mid['population_admitted']=False
            mid.to_csv(inc_middle,index=False)
    prior_new=[]
    for prior in sorted(round_dir.glob('signature_increment_*.csv')):
        prior_new.append(pd.read_csv(prior,low_memory=False))
    # A transport failure can occur after several saved raw batches but before
    # the 500-QID checkpoint. Recover just those already-fetched entities once.
    known_qids=set(base_ledger.wikidata_qid.astype(str))
    for prior in prior_new:
        if 'wikidata_qid' in prior: known_qids.update(prior.wikidata_qid.dropna().astype(str))
    missing_eval=sorted(set(already)-known_qids)
    for off in range(0,len(missing_eval),500):
        block=missing_eval[off:off+500]; blockset=set(block)
        block_pairs=pairs[pairs.wikidata_qid.astype(str).isin(blockset)].copy()
        recovered=pd.DataFrame(evaluate_signatures(block,RAWDIR,block_pairs,profiles))
        if len(recovered):recovered['candidate_only']=True;recovered['identity_admitted']=False;recovered['population_admitted']=False
        fname=f'signature_increment_recovered_{len(known_qids)+len(block):06d}.csv'
        recovered.to_csv(round_dir/fname,index=False);prior_new.append(recovered);known_qids.update(blockset)
    for start in range(0,len(qids),50):
        batch=qids[start:start+50]
        url,final,status,body=retry_fetch(batch)
        num=next_num+start//50; fp=RAWDIR/f'raw_entity_batch_{num:02d}.json'
        # Raw response bytes are immutable and saved before parsing.
        fp.write_bytes(body); data=json.loads(body.decode('utf-8')); ents=data.get('entities',{})
        meta={'batch':num,'requested_qids':batch,'returned_qids':sorted(ents),'requested':len(batch),'returned':len(ents),'url':url,'final_url':final,'http_status':status,'raw_file':str(fp),'raw_bytes':len(body),'raw_response_sha256':sha_bytes(body),'fetched_at_utc':utc()}
        batch_meta.append(meta)
        if (start//50+1)%args.checkpoint_every_batches==0 or start+50>=len(qids):
            # Re-evaluate only the new request window; the frozen first 2k
            # signature packet remains immutable and is never rescanned.
            block_start=(start//(50*args.checkpoint_every_batches))*(50*args.checkpoint_every_batches)
            recent=qids[block_start:min(len(qids),start+50)]
            recent=set(map(str,recent))
            recent_pairs=pairs[pairs.wikidata_qid.astype(str).isin(recent)].copy()
            signatures=evaluate_signatures(sorted(recent),RAWDIR,recent_pairs,profiles)
            sdf=pd.DataFrame(signatures)
            if len(sdf):
                sdf['candidate_only']=True;sdf['identity_admitted']=False;sdf['population_admitted']=False
                for c in ['fetched_ru_label_exact','fetched_p764_exact','fetched_physical_p31','event_exact_native_code_guard']:
                    if c in sdf:sdf[c]=sdf[c].map(lambda v: str(v).casefold() in {'true','1','yes','t'})
                sdf['review_candidate_eligible']=sdf.matching_source_pair_count.eq(1)&sdf.fetched_ru_label_exact.fillna(False)&sdf.fetched_p764_exact.fillna(False)&sdf.fetched_physical_p31.fillna(False)&~sdf.event_exact_native_code_guard.fillna(True)&~sdf.current_to_2002_uf_outcome.eq('year_constrained_collision')&~sdf.current_to_2010_uf_outcome.eq('year_constrained_collision')
            inc=round_dir/f'signature_increment_{len(already)+start+len(batch):06d}.csv'
            sdf.to_csv(inc,index=False)
            prior_new.append(sdf)
            ck=round_dir/f'checkpoint_{len(already)+start+len(batch):06d}'; ck.mkdir(exist_ok=True)
            allsig=pd.concat([base_ledger,*prior_new],ignore_index=True,sort=False)
            allsig.to_csv(ck/'cumulative_signature_review_candidates.csv',index=False)
            allmeta=[]
            for m in sorted(RAWDIR.glob('raw_entity_batch_*.json'))[-args.checkpoint_every_batches:]:
                b=m.read_bytes(); ed=json.loads(b.decode('utf-8')).get('entities',{})
                for q,e in ed.items():
                    if str(q) not in recent: continue
                    claims=e.get('claims',{}); rawp31=[]; rawp764=[]
                    for s in claims.get('P31',[]):
                        try:
                            if s.get('rank')!='deprecated': rawp31.append(s['mainsnak']['datavalue']['value']['id'])
                        except Exception: pass
                    for s in claims.get('P764',[]):
                        try:
                            if s.get('rank')!='deprecated': rawp764.append(digits(s['mainsnak']['datavalue']['value']))
                        except Exception: pass
                    allmeta.append({'wikidata_qid':q,'raw_batch':m.name,'raw_batch_sha256':sha_bytes(b),'raw_entity_sha256':sha_bytes(json.dumps(e,ensure_ascii=False,separators=(',',':')).encode()),'label_ru':e.get('labels',{}).get('ru',{}).get('value',''),'P764_values_json':json.dumps(rawp764),'P31_qids_json':json.dumps(rawp31),'physical_P31':any(profiles.get(x,{}).get('physical_settlement_lineage') for x in rawp31)})
            pd.DataFrame(allmeta).to_csv(ck/'fetched_entity_metadata_increment.csv',index=False)
            rec={'status':'progressive_candidate_only_review_checkpoint','raw_qids_fetched':len(current_raw_qids()),'new_request_qids_completed':len(already)+start+len(batch)-len(already),'expanded_qids_new_fetch_target':len(request),'increment_signature_rows':len(sdf),'cumulative_signature_rows':len(allsig),'increment_single_pair_signature_rows':int((sdf.get('statement_status',pd.Series(dtype=str))=='unique_source_pair_signature').sum()),'cumulative_single_pair_signature_rows':int((allsig.get('statement_status',pd.Series(dtype=str))=='unique_source_pair_signature').sum()),'raw_batches_sha256':sha_bytes(json.dumps([{'file':m.name,'sha256':sha(m)} for m in sorted(RAWDIR.glob('raw_entity_batch_*.json'))],sort_keys=True).encode()),'signature_csv_sha256':sha(ck/'cumulative_signature_review_candidates.csv'),'metadata_csv_sha256':sha(ck/'fetched_entity_metadata_increment.csv'),'source_pair_checkpoint_sha256':sha(PAIR_CHECKPOINT),'request_sha256':sha(request_path),'all_admission_flags_false':True}
            (ck/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({'checkpoint':str(ck),'raw_qids_fetched':rec['raw_qids_fetched'],'increment_signature_rows':len(sdf),'cumulative_single_pair_signature_rows':rec['cumulative_single_pair_signature_rows'],'latest_batch_hash':meta['raw_response_sha256']},ensure_ascii=False),flush=True)
            if start+50<len(qids): time.sleep(10.0)
        elif start+50<len(qids): time.sleep(6.0)

if __name__=='__main__': main()
