"""Apply source-bound aliases and typed lifecycle routes without changing counts."""
from pathlib import Path
import argparse, hashlib, json, math, sys, time
import pandas as pd
ROOT=Path(__file__).resolve().parents[3];E=ROOT/'research_rebuild/evidence'
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import State, distance_km
from build_long_table import UnionFind, ACCEPTED_COORDINATE_STATUSES
CONTROLS={2002:145166731,2010:142856536,2021:144699673}
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--previous-full',required=True);ap.add_argument('--output',required=True);ap.add_argument('--full-output',required=True);args=ap.parse_args()
    start=time.monotonic();out=Path(args.output);full=Path(args.full_output);out.mkdir(parents=True,exist_ok=True);full.mkdir(parents=True,exist_ok=True);base=Path(args.previous_full);pins={}
    def pin(p):
        p=Path(p);pins[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size};return p
    def read(p,**kw):return pd.read_csv(pin(p),keep_default_na=False,**kw)
    obs=pd.read_parquet(pin(base/'applied_state_observations.parquet'));original=obs.drop(columns='root').copy(deep=True);assert obs.source_record_id.is_unique
    s=State.__new__(State);s.obs=obs;s.by_id=obs.set_index('source_record_id',drop=False);s.uf=UnionFind(obs.source_record_id);s.uf.parent=dict(zip(obs.source_record_id,obs.root));s.years={}
    for root,y in zip(obs.root,obs.census_year):s.years.setdefault(root,set()).add(int(y))
    p=pd.read_parquet(pin(base/'applied_core_point_snapshot.parquet')).fillna('');s.point_rows={}
    for r in p.to_dict('records'):
        sid=r.pop('source_record_id');assert r['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES;s.point_rows[sid]=r
    s.point_alternatives=[];s.conflicting_point_targets=set();s.inputs=[]
    assert len(obs)==465929 and len(s.point_rows)==447366
    scopes=read(ROOT/'publication/stage71/accepted_large_record_scope_classification_overlay.csv');scope2=read(E/'over500_route_audit_20261009/accepted_scope_overlay.csv');scopeids=set(scopes.source_record_id)|set(scope2.source_record_id)
    def complete():
        a=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','крым','севастополь'])&~s.obs.source_record_id.isin(scopeids)].copy()
        a['has_point']=a.source_record_id.isin(s.point_rows);a['finite']=a.population.notna()
        st=a.groupby('root').agg(n=('source_record_id','size'),years=('census_year','nunique'),points=('has_point','all'),finite=('finite','all'))
        roots=set(st[(st.n==3)&(st.years==3)&st.points&st.finite].index)
        return set(a.loc[a.root.isin(roots),'source_record_id']),roots
    oldfull,oldroots=complete();assert len(oldroots)==142735
    edgeframes=[]
    for rel in ['remaining_alias_center_round2_20261013/accepted_identity_edge_delta.csv','remaining_alias_eastnorth_round2_20261013/accepted_identity_edge_delta.csv','remaining_alias_volga_round2_20261013/accepted_identity_edge_proposals.csv','remaining_alias_south_round2_20261013/accepted_identity_edge_proposals.csv','remaining_moscow_close_round2_20261013/proposed_identity_edge.csv']:
        f=read(E/rel);f=f.rename(columns={'left_source_record_id':'from_source_record_id','right_source_record_id':'to_source_record_id','source_record_id_a':'from_source_record_id','source_record_id_b':'to_source_record_id'})
        assert f.from_source_record_id.notna().all() and f.to_source_record_id.notna().all()
        f['original_packet_decision_status']=f.decision_status;f['decision_status']='checked_rule_accepted';f['relation']='same_place';f['input_packet']=str(E/rel)
        # Fresh source captures are checked byte-for-byte before admission.
        for r in f.to_dict('records'):
            for pk,hk in [('evidence_path','evidence_sha256'),('evidence_file','evidence_sha256'),('source_path','source_sha256'),('primary_witness_path','primary_witness_sha256')]:
                if r.get(pk) and r.get(hk) and isinstance(r[pk],str) and isinstance(r[hk],str):
                    q=Path(r[pk]);q=q if q.is_absolute() else ROOT/q;assert sha(pin(q))==r[hk]
        edgeframes.append(f)
    edges=pd.concat(edgeframes,ignore_index=True).fillna('');edges.to_csv(out/'applied_identity_edges.csv',index=False)
    repair=read(E/'remaining_alias_volga_round2_20261013/point_repair_proposals.csv').rename(columns={'source_record_id':'target_source_record_id'})
    assert len(repair)==1;sid=repair.target_source_record_id.iloc[0];assert sid.endswith(':!!!:12204')
    old=s.point_rows[sid];assert (float(old['latitude']),float(old['longitude']))==(57.593341,52.522646)
    assert distance_km((old['latitude'],old['longitude']),(float(repair.latitude.iloc[0]),float(repair.longitude.iloc[0])))>50
    for row in repair.to_dict('records'):assert sha(pin(row['point_origin_file']))==row['point_origin_sha256']
    rejected=[dict(target_source_record_id=sid,old_latitude=old['latitude'],old_longitude=old['longitude'],old_point_origin_file=old['point_origin_file'],old_point_origin_sha256=old['point_origin_sha256'],old_point_origin_locator=old['point_origin_locator'],rejection_status='reviewed_rejected_coordinate_claim_only',reason='Current point belongs to Krasnogorsky namesake; independently native-source-bound Uvinsky own article, county/flanks and separate village rival establish replacement. Native census count retained.')]
    del s.point_rows[sid];repair['coordinate_admission_status']='reviewed_extension_rule_accepted';repair['point_use_inference']='Own-place representative point, retrospective spatial continuity from independently sourced alias/native context; no exact census-day measurement.';repair['external_provider_ID_binding_asserted']=False;repair['population_boundary_comparability_asserted']=False
    eastpoints=read(E/'remaining_alias_eastnorth_round2_20261013/accepted_point_use_delta.csv');newpoints=pd.concat([repair,eastpoints],ignore_index=True).fillna('');newpoints.to_csv(out/'applied_point_use_delta.csv',index=False)
    s.add_deltas(edge_paths=[out/'applied_identity_edges.csv'],point_paths=[out/'applied_point_use_delta.csv'])
    pd.testing.assert_frame_equal(original,s.obs.drop(columns='root'));newfull,newroots=complete();assert oldfull<=newfull
    overlay=read(ROOT/'publication/stage71/applied_primary_population_source_overlay_2010.csv.gz').set_index('original_source_record_id')
    actual=s.obs.copy();actual['effective_population']=actual.source_record_id.map(overlay.population).combine_first(actual.population)
    actual['accepted_point_present']=actual.source_record_id.isin(s.point_rows);actual['accepted_latitude']=actual.source_record_id.map(lambda sid:s.point_rows.get(sid,{}).get('latitude',float('nan')));actual['accepted_longitude']=actual.source_record_id.map(lambda sid:s.point_rows.get(sid,{}).get('longitude',float('nan')))
    actual['finite_ordinary_full3_all_ownpoints']=actual.source_record_id.isin(newfull);native=actual.set_index('source_record_id')
    seed=read(E/'residual_root_20261013/applied/integrated_credited_UID_roster.csv.gz');seedids=set(seed.source_record_id);ids=seedids|newfull
    # Typed events supplement the existing working axis, never ordinary UF.
    events=[];routes=[];availability=[]
    novo=read(E/'remaining_alias_south_round2_20261013/accepted_inclusion_event_proposals.csv').iloc[0].to_dict()
    ep=Path(novo['event_source_file']);assert sha(pin(ep))==novo['event_source_sha256'];pin(E/'remaining_alias_south_round2_20261013/novo_ispik_event_witness.json');pin(E/'remaining_alias_south_round2_20261013/novo_ispik_2005_law.html')
    donor='2002:029_fe8710371d_02c_Dagestan.xls:2002:1832';recipient='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:17709'
    assert native.loc[donor,'settlement_name']=='Новый Испик' and native.loc[recipient,'settlement_name']=='Испик';assert donor in s.point_rows and recipient in s.point_rows
    assert float(native.loc[donor,'population'])==921 and int(native.loc[recipient,'census_year'])==2021
    events.append(dict(novo,primary_law_role='roster-removal corroboration; explicit NP inclusion interval is the own-article statement',graph_union_allowed=False,event_kind='included_in'))
    routes.append(dict(source_record_id=donor,route_kind='dated_own_locality_included_in',scope_id=novo['scope_id'],recipient_source_record_id=recipient,recipient_population_assigned=False,graph_union_allowed=False));ids.add(donor)
    for y in [2002,2010,2021]:availability.append(dict(scope_id=novo['scope_id'],census_year=y,status='observed_own_count' if y==2002 else 'not_separately_applicable_after_inclusion',own_population=921 if y==2002 else '',predecessor_population_unknown=False))
    quotes=read(E/'remaining_moscow_close_round2_20261013/event_source_quotes.csv').set_index('article')
    # Restoration of a named legal entity does not imply the physical place was
    # absent before2002. Earlier predecessor identity/count stays explicitly unknown.
    for nm,current,old,article in [
        ('Исаково','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:68495','2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:11496','Исаково_(Богородский_городской_округ)'),
        ('Марьино','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:68508','2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:11497','Марьино_(Богородский_городской_округ)')]:
        assert s.uf.find(current)==s.uf.find(old) and s.years[s.uf.find(old)]=={2010,2021};assert native.loc[current,'settlement_name']==nm
        row=quotes.loc[article];source=E/'remaining_moscow_close_round2_20261013'/f'{article}.html';assert sha(pin(source))==row['sha256_html'];assert 'вновь образована' in row['quote']
        scope='round2_reinstated_'+nm;events.append(dict(scope_id=scope,event_kind='named_legal_entity_reinstated',event_date='2009–2010',date_precision='documented_legal_interval',quoted_federal_naming_date='2009-08-08',quoted_regional_amendment_date='2010-09-23',operative_day_not_asserted=True,event_source_file=str(source),event_source_sha256=sha(source),event_source_locator=row['locator'],literal_quote=row['quote'],physical_place_birth_asserted=False,graph_union_allowed=False))
        for record in [old,current]:
            assert record in s.point_rows and math.isfinite(float(native.loc[record,'population']));ids.add(record);routes.append(dict(source_record_id=record,route_kind='available_observed_census_chain_since_named_legal_reinstatement',scope_id=scope,graph_union_allowed=False))
        for y in [2002,2010,2021]:availability.append(dict(scope_id=scope,census_year=y,status='UNKNOWN_prior_entity_and_population' if y==2002 else 'observed_own_count',own_population='' if y==2002 else float(native.loc[old if y==2010 else current,'population']),predecessor_population_unknown=y==2002))
    # Two predecessor places remain separate. Only the observed merged successor
    # is credited through its dated source-backed event and own representative point.
    article='Орешково_(Луховицкий_район)';row=quotes.loc[article];source=E/'remaining_moscow_close_round2_20261013'/f'{article}.html';assert sha(pin(source))==row['sha256_html'] and 'единый сельский населённый пункт' in row['quote']
    successor='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:68202';assert native.loc[successor,'settlement_name']=='Орешково' and native.loc[successor,'settlement_type']=='посёлок' and successor in s.point_rows
    predecessors=['2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:2881','2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:2882','2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:10678','2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:10682']
    assert all(x in native.index for x in predecessors)
    # The farm's two old observations are linked; the old village observations
    # are still separate native components. Preserve that actual state rather
    # than silently manufacturing a village bridge or two precursor roots.
    assert s.uf.find(predecessors[1])==s.uf.find(predecessors[3])
    assert s.uf.find(predecessors[0])!=s.uf.find(predecessors[1])
    assert s.uf.find(successor) not in {s.uf.find(x) for x in predecessors}
    events.append(dict(scope_id='round2_oreshkovo_merged_successor',event_kind='merged_into',event_date='2011-03-22',date_precision='quoted_act_date',operative_day_not_asserted=True,event_source_file=str(source),event_source_sha256=sha(source),event_source_locator=row['locator'],literal_quote=row['quote'],predecessor_source_record_ids=json.dumps(predecessors),quoted_exact_official_2010_combined_count=731,protected_selected_2010_predecessor_sum=729,population_sum_equivalence_asserted=False,graph_union_allowed=False))
    ids.add(successor);routes.append(dict(source_record_id=successor,route_kind='dated_merger_observed_successor',scope_id='round2_oreshkovo_merged_successor',predecessor_counts_reassigned=False,graph_union_allowed=False))
    for y in [2002,2010,2021]:availability.append(dict(scope_id='round2_oreshkovo_merged_successor',census_year=y,status='predecessors_observed_separately_no_synthetic_successor_count' if y<2021 else 'observed_merged_successor',own_population=632 if y==2021 else '',predecessor_population_unknown=False))
    pd.DataFrame(events).to_csv(out/'applied_typed_events.csv',index=False);pd.DataFrame(routes).to_csv(out/'applied_typed_native_credit_routes.csv',index=False);pd.DataFrame(availability).to_csv(out/'typed_available_year_statuses.csv',index=False)
    assert not ids&set(scopes.source_record_id[scopes.region_norm.isin(['москва','санкт петербург'])]) if 'region_norm' in scopes else True
    gained=ids-seedids;assert seedids<=ids;actual['working_credit_present']=actual.source_record_id.isin(ids);actual['new_credit_this_application']=actual.source_record_id.isin(gained)
    f=read(ROOT/'publication/stage71/accepted_common_federal_territory_axis.csv');assert len(f)==6 and f.population_source_record_id.is_unique and not set(f.population_source_record_id)&ids;fed=f.groupby('census_year').territory_population.sum().to_dict()
    previous=read(E/'residual_root_20261013/applied/coverage.csv').set_index('census_year');coverage=[]
    for y,den in CONTROLS.items():
        n=int(actual.loc[actual.census_year.eq(y)&actual.working_credit_present,'effective_population'].sum()+fed[y]);coverage.append(dict(census_year=y,credited_population=n,denominator=den,coverage_percent=100*n/den,remaining_to_100=den-n,net_population_gain=n-int(previous.loc[y,'credited_population'])))
    pd.DataFrame(coverage).to_csv(out/'coverage.csv',index=False)
    cols=['source_record_id','census_year','effective_population','root','finite_ordinary_full3_all_ownpoints','accepted_point_present','working_credit_present','new_credit_this_application'];actual.loc[actual.working_credit_present,cols].sort_values('source_record_id').to_csv(out/'integrated_credited_UID_roster.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    actual[actual.source_record_id.isin(gained)].to_csv(out/'new_credit_native_records.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    initial=read(E/'residual_root_20261013/applied/remaining_initial_over500_residual.csv.gz');remaining=actual[actual.source_record_id.isin(initial.source_record_id)&~actual.working_credit_present];remaining.to_csv(out/'remaining_initial_over500_residual.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(rejected).to_csv(out/'point_use_rejections.csv',index=False)
    actual.to_parquet(full/'integrated_spatial_temporal_records.parquet',index=False,compression='zstd');s.obs.to_parquet(full/'applied_state_observations.parquet',index=False,compression='zstd')
    fields=['latitude','longitude','coordinate_admission_status','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_ledger_path'];pd.DataFrame([dict(source_record_id=sid,**{k:r.get(k,'') for k in fields}) for sid,r in s.point_rows.items()]).to_parquet(full/'applied_core_point_snapshot.parquet',index=False,compression='zstd')
    ratios=[]
    for r in edges.to_dict('records'):
        a,b=native.loc[r['from_source_record_id']],native.loc[r['to_source_record_id']];x,y=float(a.effective_population),float(b.effective_population)
        ratios.append(dict(from_source_record_id=a.name,to_source_record_id=b.name,from_population=x,to_population=y,ratio=y/x if x else '',extreme_flag=(x==0 and y>0) or(x>0 and y/x>21)or(y==0 and x>0)or(y>0 and x/y>21)))
    pd.DataFrame(ratios).to_csv(out/'new_edge_population_ratio_screen.csv',index=False)
    receipt={'status':'applied_source_bound_alias_and_lifecycle_round2','source_fields_counts_quality_unchanged':True,'ordinary_full3_before':len(oldroots),'ordinary_full3_after':len(newroots),'applied_identity_edge_rows':len(edges),'new_credited_UIDs':len(gained),'final_credited_native_UIDs':len(ids),'active_ownpoints':len(s.point_rows),'new_point_uses':1,'wrong_namesake_point_uses_corrected':1,'typed_event_scopes':len(events),'typed_route_unique_UIDs':len({r['source_record_id'] for r in routes}),'initial_residual_records':len(initial),'initial_residual_records_resolved':len(initial)-len(remaining),'remaining_residual_records':len(remaining),'extreme_ratio_flags':sum(r['extreme_flag'] for r in ratios),'coverage':coverage,'federal_rows_counted_once':6,'input_pins':pins,'full_output_hashes':{p.name:sha(p) for p in full.glob('*.parquet')},'runtime_seconds':round(time.monotonic()-start,3),'caution':'Typed reinstatement has UNKNOWN pre2002 predecessor/count; no physical birth, fabricated zero, population allocation, or ordinary union of merger predecessors.'}
    (out/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='input_pins'},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
