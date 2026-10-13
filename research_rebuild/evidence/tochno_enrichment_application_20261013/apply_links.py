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
    assert len(obs)==465929 and len(s.point_rows)==447367
    scopes=read(ROOT/'publication/stage71/accepted_large_record_scope_classification_overlay.csv');scope2=read(E/'over500_route_audit_20261009/accepted_scope_overlay.csv');scopeids=set(scopes.source_record_id)|set(scope2.source_record_id)
    def complete():
        a=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','крым','севастополь'])&~s.obs.source_record_id.isin(scopeids)].copy()
        a['has_point']=a.source_record_id.isin(s.point_rows);a['finite']=a.population.notna()
        st=a.groupby('root').agg(n=('source_record_id','size'),years=('census_year','nunique'),points=('has_point','all'),finite=('finite','all'))
        roots=set(st[(st.n==3)&(st.years==3)&st.points&st.finite].index)
        return set(a.loc[a.root.isin(roots),'source_record_id']),roots
    oldfull,oldroots=complete();assert len(oldroots)==142759
    edges=read(E/'mass_onepoint_round4_20261013/accepted_identity_edge_delta.csv');points=read(E/'mass_onepoint_round4_20261013/accepted_point_use_delta.csv')
    assert len(edges)==6 and len(points)==6 and set(edges.decision_status)=={'checked_rule_accepted'}
    for r in points.to_dict('records'):
        sid=r['target_source_record_id'];donor=r['coordinate_source_record_id'];assert sid not in s.point_rows and donor in s.point_rows
        assert (float(r['latitude']),float(r['longitude']))==(float(s.point_rows[donor]['latitude']),float(s.point_rows[donor]['longitude']))
        assert sha(pin(r['coordinate_origin_ledger']))==r['coordinate_origin_ledger_sha256']
    edges.to_csv(out/'applied_identity_edges.csv',index=False);points.to_csv(out/'applied_point_use_delta.csv',index=False)
    s.add_deltas(edge_paths=[out/'applied_identity_edges.csv'],point_paths=[out/'applied_point_use_delta.csv'])
    pd.testing.assert_frame_equal(original,s.obs.drop(columns='root'));newfull,newroots=complete();assert oldfull<=newfull
    actual=pd.read_parquet(pin(base/'integrated_spatial_temporal_records.parquet'));actual['root']=actual.source_record_id.map(s.obs.set_index('source_record_id').root)
    actual['accepted_point_present']=actual.source_record_id.isin(s.point_rows)
    actual['accepted_latitude']=actual.source_record_id.map(lambda sid:s.point_rows.get(sid,{}).get('latitude',float('nan')))
    actual['accepted_longitude']=actual.source_record_id.map(lambda sid:s.point_rows.get(sid,{}).get('longitude',float('nan')))
    actual['finite_ordinary_full3_all_ownpoints']=actual.source_record_id.isin(newfull)
    seed=read(E/'remaining_round2_root_20261013/applied/integrated_credited_UID_roster.csv.gz');seedids=set(seed.source_record_id);ids=seedids|newfull;gained=ids-seedids
    assert len(gained)==16 and seedids<=ids
    actual['working_credit_present']=actual.source_record_id.isin(ids);actual['new_credit_this_application']=actual.source_record_id.isin(gained)
    f=read(ROOT/'publication/stage71/accepted_common_federal_territory_axis.csv');assert len(f)==6 and not set(f.population_source_record_id)&ids;fed=f.groupby('census_year').territory_population.sum().to_dict()
    previous=read(E/'remaining_round2_root_20261013/applied/coverage.csv').set_index('census_year');coverage=[]
    for y,den in CONTROLS.items():
        n=int(actual.loc[actual.census_year.eq(y)&actual.working_credit_present,'effective_population'].sum()+fed[y]);gain=n-int(previous.loc[y,'credited_population']);assert gain=={2002:280,2010:157,2021:79}[y]
        coverage.append(dict(census_year=y,credited_population=n,denominator=den,coverage_percent=100*n/den,remaining_to_100=den-n,net_population_gain=gain))
    pd.DataFrame(coverage).to_csv(out/'coverage.csv',index=False)
    cols=['source_record_id','census_year','effective_population','root','finite_ordinary_full3_all_ownpoints','accepted_point_present','working_credit_present','new_credit_this_application']
    actual.loc[actual.working_credit_present,cols].sort_values('source_record_id').to_csv(out/'integrated_credited_UID_roster.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    actual[actual.source_record_id.isin(gained)].to_csv(out/'new_credit_native_records.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    actual.to_parquet(full/'integrated_spatial_temporal_records.parquet',index=False,compression='zstd');s.obs.to_parquet(full/'applied_state_observations.parquet',index=False,compression='zstd')
    fields=['latitude','longitude','coordinate_admission_status','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_ledger_path']
    pd.DataFrame([dict(source_record_id=sid,**{k:r.get(k,'') for k in fields}) for sid,r in s.point_rows.items()]).to_parquet(full/'applied_core_point_snapshot.parquet',index=False,compression='zstd')
    receipt={'status':'applied_onepoint_unique_county_continuity','source_fields_counts_quality_unchanged':True,'ordinary_full3_before':len(oldroots),'ordinary_full3_after':len(newroots),'applied_identity_edge_rows':len(edges),'new_credited_UIDs':len(gained),'final_credited_native_UIDs':len(ids),'active_ownpoints':len(s.point_rows),'new_point_uses':6,'coverage':coverage,'federal_rows_counted_once':6,'input_pins':pins,'full_output_hashes':{p.name:sha(p) for p in full.glob('*.parquet')},'runtime_seconds':round(time.monotonic()-start,3)}
    (out/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='input_pins'},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
