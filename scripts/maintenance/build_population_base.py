"""Reconstruct the accepted 2026-10-13 census state from frozen published packets.

This is a replay of accepted decisions, not fresh admission or rereading of raw
XLS/HTML evidence. Every packet is hash-pinned. No population value is inferred.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def build(source, output, manifest):
    for item in manifest['inputs']:
        p = source / item['path']
        assert p.stat().st_size == item['bytes'] and digest(p) == item['sha256'], str(p)
    sys.path.insert(0, str(source/'research_rebuild/mass_linkage'))
    from build_long_table import UnionFind, ACCEPTED_COORDINATE_STATUSES
    from current_chain_state_20261007 import State
    def read(path):
        return pd.read_csv(source/path, keep_default_na=False, low_memory=False)
    base = 'publication/stage71/'
    s = State.__new__(State)
    s.obs = pd.read_parquet(source/(base+'applied_state_observations.parquet'))
    s.uf = UnionFind(s.obs.source_record_id)
    s.uf.parent = dict(zip(s.obs.source_record_id, s.obs.root))
    s.years = {}
    for root, year in zip(s.obs.root, s.obs.census_year):
        s.years.setdefault(root, set()).add(int(year))
    import pyarrow.parquet as pq
    point_path=source/(base+'applied_point_snapshot.parquet')
    keep=['source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_ledger_path']
    p = pd.read_parquet(point_path,columns=[x for x in keep if x in pq.ParquetFile(point_path).schema_arrow.names])
    # Preserve point provenance core fields without enormous sparse legacy columns.
    fields = ['latitude','longitude','coordinate_admission_status','coordinate_source_record_id',
              'point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_ledger_path']
    s.point_rows = {r['source_record_id']: {k:r.get(k, '') for k in fields}
                    for r in p[[x for x in ['source_record_id',*fields] if x in p]].fillna('').to_dict('records')}
    for row in s.point_rows.values():
        row['latitude']=float(row['latitude']);row['longitude']=float(row['longitude'])
    s.point_alternatives=[];s.conflicting_point_targets=set();s.inputs=[]
    def refresh():
        s.obs['root'] = s.obs.source_record_id.map(s.uf.find)
        s.by_id = s.obs.set_index('source_record_id',drop=False)
    def partition(before, after):
        actual = set(s.obs.loc[s.obs.source_record_id.map(s.uf.find).eq(s.uf.find(before[0])), 'source_record_id'])
        assert actual == set(before)
        flat = [sid for group in after for sid in group]
        assert len(flat)==len(set(flat)) and set(flat)==actual
        s.years.pop(s.uf.find(before[0]))
        for sid in before:
            s.uf.parent[sid]=sid;s.years[sid]={int(s.by_id.loc[sid,'census_year'])}
        for group in after:
            for sid in group[1:]:s.union(group[0],sid)
        refresh()
    refresh()
    recipe=manifest['recipe']
    for path in recipe.get('observations',[]):
        frame=read(path)
        assert not set(frame.source_record_id)&set(s.obs.source_record_id)
        assert frame.source_record_id.is_unique and frame.source_sha256.ne('').all() and frame.source_locator.ne('').all()
        for row in frame.to_dict('records'):
            assert int(row['census_year']) in {2002,2010,2021} and float(row['population'])>=0
            s.uf.parent[row['source_record_id']]=row['source_record_id']
            s.years[row['source_record_id']]={int(row['census_year'])}
        for col in ['census_year','population']:frame[col]=frame[col].astype(s.obs[col].dtype)
        frame['is_additive_settlement_record']=True;frame['root']=frame.source_record_id
        for col in ['latitude','longitude']:frame[col]=pd.to_numeric(frame[col],errors='coerce')
        s.obs=pd.concat([s.obs,frame.reindex(columns=s.obs.columns)],ignore_index=True)
    refresh()
    frozen_source_fields=s.obs.drop(columns='root').copy(deep=True)
    for path in recipe.get('component_partitions',[]):
        for row in read(path).to_dict('records'):
            assert row['admission_status']=='reviewed_wrong_identity_component_partition_correction'
            partition(json.loads(row['expected_before_members_JSON']),json.loads(row['after_partition_JSON']))
    for path in recipe.get('point_rejections',[]):
        for row in read(path).to_dict('records'):
            sid=row['target_source_record_id'];old=s.point_rows[sid]
            assert (float(old['latitude']),float(old['longitude']))==(float(row['old_latitude']),float(row['old_longitude']))
            del s.point_rows[sid]
    s.add_deltas(edge_paths=[source/p for p in recipe['edges']],point_paths=[source/p for p in recipe['points']])
    assert len(s.obs)==465929 and len(s.point_rows)==447362
    for phase in manifest['phases']:
        if phase.get('partitions'):
            for row in json.loads((source/phase['partitions']).read_text()):
                partition(row['expected_current_full_members'],row['after_partitions'])
        for path in phase.get('point_rejections',[]):
            for row in read(path).to_dict('records'):
                sid=row['target_source_record_id'];old=s.point_rows[sid]
                assert (float(old['latitude']),float(old['longitude']))==(float(row['old_latitude']),float(row['old_longitude']))
                del s.point_rows[sid]
        point_paths=[source/p for p in phase['points']]
        # Frozen residual application explicitly superseded the distinct homonym point.
        for path in point_paths:
            for row in pd.read_csv(path,keep_default_na=False).to_dict('records'):
                sid=row['target_source_record_id']
                if sid in s.point_rows:
                    old=s.point_rows[sid]
                    from current_chain_state_20261007 import distance_km
                    if distance_km((float(row['latitude']),float(row['longitude'])),(float(old['latitude']),float(old['longitude'])))>5:
                        assert sid in phase.get('accepted_large_point_replacements',[]), sid
                        del s.point_rows[sid]
        s.add_deltas(edge_paths=[source/p for p in phase['edges']],point_paths=point_paths)
        assert len(s.point_rows)==phase['active_ownpoints']
    pd.testing.assert_frame_equal(frozen_source_fields,s.obs.drop(columns='root'))
    assert s.obs.source_record_id.is_unique and len(s.point_rows)==447373
    roster=read(manifest['final_roster']);assert roster.source_record_id.is_unique and len(roster)==431948
    obs=s.obs.copy();overlay=read(base+'applied_primary_population_source_overlay_2010.csv.gz').set_index('original_source_record_id')
    obs['effective_population']=obs.source_record_id.map(overlay.population).combine_first(obs.population)
    obs['population_overlay_applied']=obs.source_record_id.isin(overlay.index)
    ids=set(roster.source_record_id);obs['working_credit_present']=obs.source_record_id.isin(ids)
    obs['accepted_point_present']=obs.source_record_id.isin(s.point_rows)
    for col in fields:
        name = 'accepted_'+col if col in {'latitude','longitude'} else col
        obs[name]=obs.source_record_id.map({sid:r.get(col) for sid,r in s.point_rows.items()})
    scopes=set(read(base+'accepted_large_record_scope_classification_overlay.csv').source_record_id)|set(read('research_rebuild/evidence/over500_route_audit_20261009/accepted_scope_overlay.csv').source_record_id)
    ordinary=obs[obs.is_additive_settlement_record.fillna(False)&~obs.region_norm.isin(['москва','санкт петербург','крым','севастополь'])&~obs.source_record_id.isin(scopes)].copy()
    ordinary['finite']=ordinary.population.notna()
    groups=ordinary.groupby('root').agg(n=('source_record_id','size'),years=('census_year','nunique'),points=('accepted_point_present','all'),finite=('finite','all'))
    roots=set(groups[(groups.n==3)&(groups.years==3)&groups.points&groups.finite].index)
    assert len(roots)==142765
    fullids=set(ordinary.loc[ordinary.root.isin(roots),'source_record_id'])
    obs['finite_ordinary_full3_all_ownpoints']=obs.source_record_id.isin(fullids)
    for prefix in [str(source)+'/', '/workspace/russian-settlements-research/']:
        obs['point_ledger_path']=obs['point_ledger_path'].map(lambda x:x[len(prefix):] if isinstance(x,str) and x.startswith(prefix) else x)
    indexed=obs.set_index('source_record_id').loc[roster.source_record_id]
    assert indexed.root.tolist()==roster.root.tolist()
    assert indexed.effective_population.astype(float).tolist()==roster.effective_population.astype(float).tolist()
    for flag in ['accepted_point_present','finite_ordinary_full3_all_ownpoints','working_credit_present']:
        assert indexed[flag].tolist()==roster[flag].map(lambda x:str(x).lower()=='true').tolist(),flag
    fed=read(base+'accepted_common_federal_territory_axis.csv');assert len(fed)==6 and not set(fed.population_source_record_id)&ids
    expected=manifest['expected_coverage'];coverage=[]
    for row in expected:
        year=row['census_year'];value=int(obs.loc[obs.census_year.eq(year)&obs.working_credit_present,'effective_population'].sum()+fed.loc[fed.census_year.eq(year),'territory_population'].sum())
        assert value==row['credited_population']
        coverage.append(dict(row,coverage_percent=100*value/row['denominator'],remaining_to_100=row['denominator']-value))
    assert not obs.duplicated(['root','census_year']).any()
    columns=['source_record_id','settlement_name','settlement_type','region_norm','district_raw','population','effective_population','population_value_quality','population_overlay_applied','accepted_latitude','accepted_longitude','accepted_point_present','working_credit_present','finite_ordinary_full3_all_ownpoints','oktmo','okato']
    wide=obs.set_index(['root','census_year'])[columns].unstack('census_year')
    wide.columns=[f'{name}_{year}' for name,year in wide.columns]
    wide=wide.reset_index();wide['ordinary_full3']=wide.root.isin(roots)
    output.mkdir(parents=True,exist_ok=True)
    obs.to_parquet(output/'settlements_census_long.parquet',index=False,compression='zstd')
    wide.to_parquet(output/'settlements_census_wide.parquet',index=False,compression='zstd')
    wide[wide.ordinary_full3].to_parquet(output/'ordinary_full3.parquet',index=False,compression='zstd')
    fed.to_csv(output/'federal_territories.csv',index=False)
    pd.DataFrame(coverage).to_csv(output/'coverage.csv',index=False)
    metadata={'dataset_id':'census_population_2002_2010_2021_accepted_20261013','primary':True,
              'source_snapshot_date':'2026-10-13','reconstructed_date':'2026-10-22',
              'native_observations':len(obs),'root_rows':len(wide),'ordinary_full3':len(roots),
              'credited_native_observations':len(roster),'accepted_own_points':len(s.point_rows),
              'coverage':coverage,'raw_source_fields_preserved':True,'final_roster_exact_values_roots_flags_match':True,
              'source_manifest_sha256':digest(Path(__file__).resolve().parents[2]/'research_context/population_source_manifest.json'),
              'reconstruction_scope':'Frozen previously accepted packets replayed; original XLS/HTML not freshly revalidated. Newly serialized Parquet, not asserted byte-identical to lost local final export.',
              'historical_final_export_sha256':'8be41d46b832310fc68bc48c715e71af87e5c525fc7e1c4d7264ce71931a623a',
              'limits':['Coverage measures population under accepted working rules, not percent of settlements or identity accuracy.','142765 strict full3 histories are distinct from the broader99.5% working layer.','Federal territories remain separate; never add their constituent source rows twice.','Unknown years/counts remain missing; boundaries and lifecycle comparability are not inferred.']}
    (output/'dataset.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(metadata,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads((Path(__file__).resolve().parents[2]/'research_context/population_source_manifest.json').read_text())
    build(args.source_root.resolve(),args.output.resolve(),manifest)
